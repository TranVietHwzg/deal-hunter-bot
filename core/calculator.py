"""
Module tính toán gộp mã đa tầng (Voucher Stacking) & Đánh giá mức giảm giá thực tế
PHIÊN BẢN CHUẨN PRODUCTION: ZERO FREESHIP BẮT BUỘC
"""
from typing import Dict, Any, List
from app.core.stacking_engine import calculate_stacked_price
from app.core.junk_filter import is_freeship

def calculate_discount_value(spend_amount, voucher):
    # Loại trừ ngay nếu dính dáng freeship
    if is_freeship(voucher)[0]:
        return 0

    min_spend = float(voucher.get("min_spend") or 0.0)
    if spend_amount < min_spend:
        return 0

    d_type = str(voucher.get("discount_type", "FIXED_AMOUNT")).upper()
    d_val = float(voucher.get("discount_value") or voucher.get("discount_val") or 0.0)
    max_d = float(voucher.get("max_discount_amount") or voucher.get("max_discount") or 0.0)

    if d_type in ["PERCENTAGE", "PERCENT"]:
        discount = spend_amount * (d_val / 100.0)
        if max_d > 0:
            discount = min(discount, max_d)
        return discount
    else:
        return min(d_val, spend_amount)

def stack_vouchers_and_evaluate(product: Dict[str, Any], available_vouchers: List[Dict[str, Any]], min_discount_threshold: float = 15.0):
    """
    Tính giá thực trả sau khi gộp mã thuần túy giá sản phẩm:
    Giá Thực Trả = Giá Niêm Yết - Giảm Trực Tiếp Shop - Mã Shop - Mã Sàn - Mã Live/Ngành
    TUYỆT ĐỐI KHÔNG TÍNH FREESHIP.
    """
    baseline_price = float(product.get("baseline_market_price") or product.get("baseline_price") or product.get("current_price", 0.0))
    current_price = float(product.get("current_price") or baseline_price)
    shop_id = str(product.get("shop_id") or "")
    shop_direct = max(0.0, baseline_price - current_price) if baseline_price > current_price else 0.0

    # Lọc sạch các voucher không phải freeship
    clean_vouchers = [v for v in available_vouchers if not is_freeship(v)[0]]

    # 1. Phân loại voucher hợp lệ
    shop_vouchers = [
        v for v in clean_vouchers 
        if str(v.get("voucher_type", "")).upper() == "SHOP" and (str(v.get("shop_id", "")) == shop_id or not shop_id)
    ]
    platform_vouchers = [
        v for v in clean_vouchers 
        if str(v.get("voucher_type", "")).upper() == "PLATFORM"
    ]
    live_cat_vouchers = [
        v for v in clean_vouchers 
        if str(v.get("voucher_type", "")).upper() in ["LIVE_VIDEO", "CATEGORY", "LIVE", "VIDEO"]
    ]

    # Tìm mã tốt nhất từng tầng
    best_shop_v = max(shop_vouchers, key=lambda v: calculate_discount_value(current_price, v), default=None)
    best_plat_v = max(platform_vouchers, key=lambda v: calculate_discount_value(current_price, v), default=None)
    best_live_v = max(live_cat_vouchers, key=lambda v: calculate_discount_value(current_price, v), default=None)

    # Tính toán gộp qua Stacking Engine chuẩn
    stack_res = calculate_stacked_price(
        product_price=current_price,
        shop_direct_discount=shop_direct,
        shop_voucher=best_shop_v,
        platform_voucher=best_plat_v,
        category_live_voucher=best_live_v
    )

    final_price = stack_res["final_price"]
    savings = (baseline_price - final_price) if baseline_price > 0 else stack_res["total_savings"]
    real_discount_pct = round((savings / baseline_price) * 100.0, 1) if baseline_price > 0 else stack_res["discount_percent"]

    # Đánh giá mục tiêu
    target_mode = str(product.get("target_mode", "PERCENT")).upper()
    target_value = float(product.get("target_value", 30.0))

    if target_mode == "PERCENT":
        is_deal_ready = real_discount_pct >= target_value
    else:
        is_deal_ready = final_price <= target_value

    if real_discount_pct >= 50:
        tier_label = "🔥🔥 [SIÊU DEAL KHỦNG - GIẢM ≥ 50%]"
    elif real_discount_pct >= 30:
        tier_label = "⚡️ [DEAL NGON - GIẢM ≥ 30%]"
    else:
        tier_label = "✨ [DEAL TIẾT KIỆM]"

    applied_list = []
    for av in stack_res["applied_vouchers"]:
        applied_list.append({
            "code": av.get("id"),
            "label": f"{av.get('title')} (-{int(av.get('discount_deducted', 0)):,}đ)",
            "discount": av.get("discount_deducted"),
            "type": av.get("type")
        })

    return {
        "baseline_price": baseline_price,
        "current_price": current_price,
        "final_price": final_price,
        "savings": savings,
        "discount_percent": real_discount_pct,
        "is_deal_ready": is_deal_ready,
        "tier_label": tier_label,
        "confidence": stack_res["confidence"],
        "applied_vouchers": applied_list
    }

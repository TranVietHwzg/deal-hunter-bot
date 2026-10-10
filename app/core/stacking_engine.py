from typing import Dict, Any, List, Optional

def calculate_stacked_price(
    product_price: float,
    shop_direct_discount: float = 0.0,
    shop_voucher: Optional[Dict[str, Any]] = None,
    platform_voucher: Optional[Dict[str, Any]] = None,
    category_live_voucher: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Voucher Stacking Engine (Thuần túy giá sản phẩm - ZERO FREESHIP).
    
    Thứ tự áp dụng chuẩn TMĐT:
    1. Giá sản phẩm
    - Giảm trực tiếp của shop (Flash sale shop / giá niêm yết giảm)
    - Voucher của Shop (nếu đạt min spend)
    - Voucher của Sàn (nếu đạt min spend trên giá còn lại)
    - Voucher Ngành Hàng / Live / Video (nếu cho phép gộp)
    = Giá thực trả dự kiến.
    
    Tuyệt đối không đưa bất kỳ khoản phí vận chuyển / freeship nào vào phép tính.
    """
    if product_price <= 0:
        return {
            "final_price": 0.0,
            "total_savings": 0.0,
            "discount_percent": 0.0,
            "confidence": "CANNOT_STACK",
            "applied_vouchers": [],
            "error": "Giá sản phẩm ban đầu phải lớn hơn 0"
        }

    applied_vouchers = []
    
    # Bước 1: Trừ giảm giá trực tiếp từ shop
    direct_deduct = min(product_price, max(0.0, shop_direct_discount))
    price_after_direct = product_price - direct_deduct

    # Bước 2: Áp dụng Voucher Shop
    d_shop = 0.0
    if shop_voucher:
        min_spend = float(shop_voucher.get("min_spend") or 0.0)
        if price_after_direct >= min_spend:
            v_type = str(shop_voucher.get("discount_type", "FIXED_AMOUNT")).upper()
            v_val = float(shop_voucher.get("discount_value") or shop_voucher.get("discount_val") or 0.0)
            max_limit = float(shop_voucher.get("max_discount_amount") or shop_voucher.get("max_discount") or float('inf'))
            
            if v_type in ["PERCENTAGE", "PERCENT"]:
                d_shop = min(price_after_direct * (v_val / 100.0), max_limit)
            else:
                d_shop = min(price_after_direct, v_val)
                
            d_shop = min(price_after_direct, max(0.0, d_shop))
            applied_vouchers.append({
                "type": "SHOP_VOUCHER",
                "id": shop_voucher.get("id") or shop_voucher.get("voucher_id_on_platform"),
                "title": shop_voucher.get("title", "Voucher Shop"),
                "discount_deducted": d_shop,
                "shop_name": shop_voucher.get("shop_name"),
                "shop_id": shop_voucher.get("shop_id")
            })

    price_after_shop = price_after_direct - d_shop

    # Bước 3: Áp dụng Voucher Sàn (Toàn sàn)
    d_plat = 0.0
    if platform_voucher:
        min_spend = float(platform_voucher.get("min_spend") or 0.0)
        # Sàn thường kiểm tra min spend trên giá sau shop hoặc giá gốc tùy quy định
        if price_after_shop >= min_spend or product_price >= min_spend:
            v_type = str(platform_voucher.get("discount_type", "FIXED_AMOUNT")).upper()
            v_val = float(platform_voucher.get("discount_value") or platform_voucher.get("discount_val") or 0.0)
            max_limit = float(platform_voucher.get("max_discount_amount") or platform_voucher.get("max_discount") or float('inf'))
            
            if v_type in ["PERCENTAGE", "PERCENT"]:
                d_plat = min(price_after_shop * (v_val / 100.0), max_limit)
            else:
                d_plat = min(price_after_shop, v_val)
                
            d_plat = min(price_after_shop, max(0.0, d_plat))
            applied_vouchers.append({
                "type": "PLATFORM_VOUCHER",
                "id": platform_voucher.get("id") or platform_voucher.get("voucher_id_on_platform"),
                "title": platform_voucher.get("title", "Voucher Toàn Sàn"),
                "discount_deducted": d_plat
            })

    price_after_plat = price_after_shop - d_plat

    # Bước 4: Áp dụng Voucher Ngành Hàng / Video / Live
    d_cat = 0.0
    if category_live_voucher:
        min_spend = float(category_live_voucher.get("min_spend") or 0.0)
        if price_after_plat >= min_spend or product_price >= min_spend:
            v_type = str(category_live_voucher.get("discount_type", "FIXED_AMOUNT")).upper()
            v_val = float(category_live_voucher.get("discount_value") or category_live_voucher.get("discount_val") or 0.0)
            max_limit = float(category_live_voucher.get("max_discount_amount") or category_live_voucher.get("max_discount") or float('inf'))
            
            if v_type in ["PERCENTAGE", "PERCENT"]:
                d_cat = min(price_after_plat * (v_val / 100.0), max_limit)
            else:
                d_cat = min(price_after_plat, v_val)
                
            d_cat = min(price_after_plat, max(0.0, d_cat))
            applied_vouchers.append({
                "type": "CATEGORY_LIVE_VOUCHER",
                "id": category_live_voucher.get("id") or category_live_voucher.get("voucher_id_on_platform"),
                "title": category_live_voucher.get("title", "Voucher Ngành/Live/Video"),
                "discount_deducted": d_cat
            })

    final_price = max(0.0, price_after_plat - d_cat)
    total_savings = product_price - final_price
    discount_percent = round((total_savings / product_price) * 100.0, 1) if product_price > 0 else 0.0

    # Xác định mức độ tin cậy (Confidence)
    num_stacked = len(applied_vouchers)
    if num_stacked >= 2:
        # Kiểm tra điều kiện can_stack
        can_stack_all = True
        for v in [shop_voucher, platform_voucher, category_live_voucher]:
            if v and v.get("can_stack_with_shop") is False:
                can_stack_all = False
                break
        confidence = "VERIFIED" if can_stack_all else "NEEDS_CHECK"
    elif num_stacked == 1:
        confidence = "VERIFIED"
    else:
        confidence = "CANNOT_STACK" if (shop_voucher or platform_voucher or category_live_voucher) else "VERIFIED"

    return {
        "original_price": product_price,
        "final_price": round(final_price, 2),
        "total_savings": round(total_savings, 2),
        "discount_percent": discount_percent,
        "confidence": confidence,
        "applied_breakdown": {
            "shop_direct": round(direct_deduct, 2),
            "shop_voucher": round(d_shop, 2),
            "platform_voucher": round(d_plat, 2),
            "category_live_voucher": round(d_cat, 2)
        },
        "applied_vouchers": applied_vouchers
    }

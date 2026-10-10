"""
Module tính toán gộp mã đa tầng (Voucher Stacking) & Đánh giá mức giảm giá thực tế
"""

def calculate_discount_value(spend_amount, voucher):
    min_spend = voucher.get("min_spend", 0)
    if spend_amount < min_spend:
        return 0
    
    d_type = voucher.get("discount_type", "FIXED")
    d_val = voucher.get("discount_val", 0)
    max_d = voucher.get("max_discount", 0)
    
    if d_type == "PERCENT":
        discount = spend_amount * (d_val / 100.0)
        if max_d > 0:
            discount = min(discount, max_d)
        return discount
    else:
        return min(d_val, spend_amount)

def stack_vouchers_and_evaluate(product, available_vouchers, min_discount_threshold=30):
    """
    Tính giá thực trả sau khi gộp mã:
    Giá Thực Trả = Giá Niêm Yết - Mã Shop - Mã Sàn - Freeship
    """
    baseline_price = product.get("baseline_price") or product.get("current_price", 0)
    current_price = product.get("current_price", baseline_price)
    shop_id = str(product.get("shop_id") or "")

    applied_vouchers = []
    
    # 1. Phân loại voucher
    shop_vouchers = [v for v in available_vouchers if v.get("voucher_type") == "SHOP" and str(v.get("shop_id", "")) == shop_id and v.get("is_active", 1) == 1]
    platform_vouchers = [v for v in available_vouchers if v.get("voucher_type") in ("PLATFORM", "LIVE_VIDEO", "VIDEO", "LIVE", "CATEGORY", "CASHBACK") and v.get("is_active", 1) == 1]
    freeship_vouchers = [v for v in available_vouchers if v.get("voucher_type") == "FREESHIP" and v.get("is_active", 1) == 1]
    
    # Ưu tiên voucher xịn (giảm nhiều nhất)
    # Tầng 1: Áp mã của Shop
    best_shop_voucher = None
    best_shop_disc = 0
    for v in shop_vouchers:
        d = calculate_discount_value(current_price, v)
        if d > best_shop_disc:
            best_shop_disc = d
            best_shop_voucher = v
            
    if best_shop_voucher and best_shop_disc > 0:
        applied_vouchers.append({
            "code": best_shop_voucher.get("voucher_code", "MÃ SHOP"),
            "label": best_shop_voucher.get("label", f"Giảm {int(best_shop_disc):,}đ"),
            "discount": best_shop_disc,
            "type": "Mã Shop"
        })

    price_after_shop = max(0, current_price - best_shop_disc)

    # Tầng 2: Áp mã Sàn / Video / Live (trên giá trị sau khi trừ mã shop)
    best_plat_voucher = None
    best_plat_disc = 0
    for v in platform_vouchers:
        d = calculate_discount_value(price_after_shop, v)
        if d > best_plat_disc:
            best_plat_disc = d
            best_plat_voucher = v
            
    if best_plat_voucher and best_plat_disc > 0:
        v_type_label = best_plat_voucher.get("category") or "Mã Sàn"
        applied_vouchers.append({
            "code": best_plat_voucher.get("voucher_code", "MÃ SÀN"),
            "label": best_plat_voucher.get("label", f"Giảm {int(best_plat_disc):,}đ"),
            "discount": best_plat_disc,
            "type": v_type_label
        })

    price_after_plat = max(0, price_after_shop - best_plat_disc)

    # Tầng 3: Freeship (nếu có mã hỗ trợ ship)
    freeship_disc = 0
    if freeship_vouchers and price_after_plat > 0:
        v = freeship_vouchers[0]
        f_val = v.get("discount_val", 30000)
        freeship_disc = f_val
        applied_vouchers.append({
            "code": v.get("voucher_code", "FREESHIP"),
            "label": v.get("label", "Hỗ trợ 30.000đ vận chuyển"),
            "discount": freeship_disc,
            "type": "Freeship"
        })

    final_price = max(0, price_after_plat) # Lưu ý: giá hàng thực trả không tính âm

    # 2. Tính % giảm giá thực tế so với baseline (thị trường chuẩn)
    if baseline_price > 0:
        real_discount_pct = round(((baseline_price - final_price) / baseline_price) * 100, 1)
    else:
        real_discount_pct = 0

    # 3. Đánh giá điều kiện thỏa mãn
    target_mode = product.get("target_mode", "PERCENT")
    target_val = float(product.get("target_value", 30))
    
    is_deal_ready = False
    if target_mode == "PERCENT":
        # Điều kiện: Đạt mức % người dùng đặt VÀ tối thiểu phải >= min_discount_threshold (30%)
        if real_discount_pct >= max(target_val, min_discount_threshold):
            is_deal_ready = True
    elif target_mode == "PRICE":
        # Điều kiện: Đạt mức giá tiền người dùng muốn VÀ % giảm thực tế >= 30%
        if final_price <= target_val and real_discount_pct >= min_discount_threshold:
            is_deal_ready = True

    # 4. Phân cấp huy hiệu
    if real_discount_pct >= 70:
        tier_label = "🚨 [SẬP GIÁ XẢ KHO ≥ 70%]"
    elif real_discount_pct >= 50:
        tier_label = "⚡️ [SIÊU DEAL GIẢM NỬA GIÁ ≥ 50%]"
    elif real_discount_pct >= 30:
        tier_label = "🔥 [DEAL HỜI XỊN ≥ 30%]"
    else:
        tier_label = "TIÊU CHUẨN (< 30%)"

    return {
        "baseline_price": baseline_price,
        "current_price": current_price,
        "final_price": final_price,
        "savings": max(0, baseline_price - final_price),
        "discount_percent": real_discount_pct,
        "is_deal_ready": is_deal_ready,
        "applied_vouchers": applied_vouchers,
        "tier_label": tier_label
    }

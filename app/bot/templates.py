from typing import Dict, Any, Optional

def format_hot_voucher_alert(voucher: Dict[str, Any], example_product: Optional[Dict[str, Any]] = None) -> str:
    """
    Mẫu cảnh báo chuẩn hóa theo đúng yêu cầu:
    🔥 VOUCHER HOT — [SÀN]
    Giảm thực tế tối đa: [x]
    Đơn tối thiểu: [x]
    Loại voucher: [sàn/shop/ngành/live]
    Khả năng gộp: [có/không/cần kiểm tra]
    Giá thực trả dự kiến: [x]
    Điểm chất lượng: [x]/100
    Hết hạn: [thời gian]
    Lý do: [ngắn gọn]
    Link: [link hợp lệ]
    """
    platform = str(voucher.get("platform_id") or voucher.get("platform", "SHOPEE")).upper()
    
    # Giảm thực tế tối đa
    d_type = str(voucher.get("discount_type", "FIXED_AMOUNT")).upper()
    d_val = float(voucher.get("discount_value") or voucher.get("discount_val") or 0.0)
    max_d = float(voucher.get("max_discount_amount") or voucher.get("max_discount") or d_val)
    
    if d_type in ["PERCENTAGE", "PERCENT"]:
        discount_str = f"{int(max_d):,}đ (Giảm {d_val}%)"
    else:
        discount_str = f"{int(d_val):,}đ"

    # Đơn tối thiểu
    min_spend = float(voucher.get("min_spend") or 0.0)
    min_spend_str = f"{int(min_spend):,}đ" if min_spend > 0 else "0đ (Không giới hạn)"

    # Loại voucher
    v_type_raw = str(voucher.get("voucher_type", "PLATFORM")).upper()
    type_map = {
        "PLATFORM": "Sàn (Toàn sàn)",
        "SHOP": "Shop (Gian hàng chính hãng)",
        "CATEGORY": f"Ngành hàng ({voucher.get('category', 'Toàn ngành')})",
        "LIVE_VIDEO": "Live / Video (Áp khi xem live hoặc video)",
        "LIVE": "Shopee Live",
        "VIDEO": "Shopee Video"
    }
    v_type_str = type_map.get(v_type_raw, v_type_raw)

    # Khả năng gộp
    can_stack_shop = voucher.get("can_stack_with_shop", True)
    can_stack_plat = voucher.get("can_stack_with_platform", False)
    if can_stack_shop and can_stack_plat:
        stack_str = "Có (Gộp được cả Mã Shop và Mã Toàn Sàn)"
    elif can_stack_shop:
        stack_str = "Có (Gộp được với Voucher Shop)"
    else:
        stack_str = "Độc quyền (Cần kiểm tra trên app)"

    # Giá thực trả dự kiến (nếu có sản phẩm mẫu tính kèm)
    if example_product:
        est_price = example_product.get("final_price", 0)
        p_name = example_product.get("name", "sản phẩm mẫu")
        est_str = f"{int(est_price):,}đ (Với {p_name})"
    else:
        est_str = f"Áp dụng giảm ngay {discount_str} khi thanh toán"

    # Điểm chất lượng
    score = voucher.get("quality_score", 85)

    # Thời gian hết hạn
    end_time_str = voucher.get("end_time") or "23:59:59 hôm nay"

    # Lý do
    reasons = []
    if d_val >= 15 and d_type in ["PERCENTAGE", "PERCENT"]:
        reasons.append(f"Tỷ lệ giảm sâu {d_val}%")
    if max_d >= 100000:
        reasons.append(f"mức trần {int(max_d):,}đ cao")
    if min_spend <= 3 * max_d and min_spend > 0:
        reasons.append("đơn tối thiểu dễ đạt")
    reasons.append("bài trừ 100% freeship ảo")
    reason_str = ", ".join(reasons).capitalize() + "."

    claim_url = voucher.get("claim_url") or "https://shopee.vn/m/ma-giam-gia"

    msg = (
        f"🔥 <b>VOUCHER HOT — [{platform}]</b>\n"
        f"<b>Giảm thực tế tối đa:</b> {discount_str}\n"
        f"<b>Đơn tối thiểu:</b> {min_spend_str}\n"
        f"<b>Loại voucher:</b> {v_type_str}\n"
        f"<b>Khả năng gộp:</b> {stack_str}\n"
        f"<b>Giá thực trả dự kiến:</b> {est_str}\n"
        f"<b>Điểm chất lượng:</b> <b><u>{score}/100</u></b>\n"
        f"<b>Hết hạn:</b> {end_time_str}\n"
        f"<b>Lý do:</b> {reason_str}\n"
        f"<b>Link:</b> <a href=\"{claim_url}\">Bấm vào đây để lấy mã</a>\n\n"
        f"💡 <i>Mẹo: {voucher.get('guide', 'Lưu mã vào kho rồi tự đặt mua thủ công trên App.')}</i>"
    )
    return msg

def format_restock_alert(voucher: Dict[str, Any]) -> str:
    return (
        f"⚡️ <b>BÁO ĐỘNG MÃ HỒI SINH (RESTOCK)</b>\n\n"
        f"Voucher <b>{voucher.get('title')}</b> vừa có lượt trở lại!\n"
        f"• Điểm chất lượng: <b>{voucher.get('quality_score', 85)}/100</b>\n"
        f"• Giảm: <b>{int(voucher.get('discount_value', 0)):,}đ</b>\n"
        f"• Đơn tối thiểu: <b>{int(voucher.get('min_spend', 0)):,}đ</b>\n"
        f"🔗 <a href=\"{voucher.get('claim_url', 'https://shopee.vn')}\">BẤM VÀO LƯU MÃ NGAY LẬP TỨC</a>"
    )

from typing import Dict, Any, Optional

def format_hot_voucher_alert(voucher: Dict[str, Any], example_product: Optional[Dict[str, Any]] = None) -> str:
    """
    Mẫu cảnh báo voucher gọn gàng, làm nổi bật mã nhập tay / mã ẩn để chạm sao chép.
    Bỏ hoàn toàn việc tính điểm phức tạp.
    """
    platform = str(voucher.get("platform_id") or "SHOPEE").upper()
    title = voucher.get("title", "")
    code = voucher.get("voucher_code") or "LƯU TRÊN BANNER"
    is_hidden = voucher.get("is_hidden") == 1 or "ẨN" in title.upper() or "AN" in str(voucher.get("category", "")).upper()

    # Tính mức giảm
    d_type = str(voucher.get("discount_type", "FIXED_AMOUNT")).upper()
    d_val = float(voucher.get("discount_value") or voucher.get("discount_val") or 0.0)
    max_d = float(voucher.get("max_discount_amount") or voucher.get("max_discount") or d_val)

    if d_type in ["PERCENTAGE", "PERCENT"]:
        discount_str = f"Giảm {int(d_val)}% (Tối đa {int(max_d):,}đ)"
    else:
        discount_str = f"Giảm {int(d_val):,}đ"

    min_spend = float(voucher.get("min_spend") or 0.0)
    min_spend_str = f"Đơn từ {int(min_spend):,}đ" if min_spend > 0 else "Đơn từ 0đ"
    claim_url = voucher.get("claim_url") or "https://shopee.vn"
    category = voucher.get("category") or "Toàn sàn"

    tag = "🔑 <b>[MÃ ẨN NHẬP TAY]</b>" if is_hidden else "🔥 <b>[VOUCHER HOT]</b>"

    # Định dạng siêu gọn: 5 dòng cốt lõi
    msg = (
        f"{tag} — <b>[{platform}]</b>\n\n"
        f"🏷 <b>Mã nhập:</b> <code>{code}</code> <i>(chạm để sao chép)</i>\n"
        f"💰 <b>Mức giảm:</b> <b>{discount_str}</b>\n"
        f"🛒 <b>Điều kiện:</b> {min_spend_str} | {category}\n"
        f"🔗 <a href=\"{claim_url}\">Mở Shopee áp mã ngay</a>"
    )
    return msg

def format_deal_alert(product: Dict[str, Any], evaluation: Dict[str, Any]) -> str:
    """Mẫu cảnh báo khi một món hàng trong Watchlist đạt giá mong muốn"""
    name = product.get("name", "Sản phẩm")
    base_price = int(evaluation.get("baseline_price", 0))
    final_price = int(evaluation.get("final_price", 0))
    pct = evaluation.get("discount_percent", 0)
    savings = int(evaluation.get("savings", 0))
    p_url = product.get("product_url", "https://shopee.vn")

    vouchers_str = ""
    for v in evaluation.get("applied_vouchers", []):
        code = v.get("code") or v.get("label", "")
        vouchers_str += f"• <code>{code}</code>\n"

    msg = (
        f"🚨 <b>[KÈO THƠM ĐẠT GIÁ]</b>\n\n"
        f"📦 <b>{name}</b>\n"
        f"💵 <b>Giá gốc:</b> <s>{base_price:,}đ</s> ➔ <b><u>{final_price:,}đ</u></b> (<b>-{pct}%</b>)\n"
        f"🎉 <b>Tiết kiệm:</b> <b>{savings:,}đ</b>\n"
    )
    if vouchers_str:
        msg += f"\n🏷 <b>Các mã cần nhập/lưu:</b>\n{vouchers_str}<i>(Chạm vào mã trên để sao chép nhanh)</i>\n"

    msg += f"\n🛒 <a href=\"{p_url}\">Bấm vào đây để mua ngay</a>"
    return msg

def format_restock_alert(voucher: Dict[str, Any]) -> str:
    """Cảnh báo khi một mã vừa được mở thêm lượt"""
    code = voucher.get("voucher_code") or "LƯU TRÊN BANNER"
    claim_url = voucher.get("claim_url", "https://shopee.vn")
    return (
        f"⚡️ <b>[MÃ HỒI SINH - VỪA CÓ LƯỢT]</b>\n\n"
        f"🏷 <b>Mã:</b> <code>{code}</code> <i>(chạm để sao chép)</i>\n"
        f"📦 <b>Ưu đãi:</b> {voucher.get('title')}\n"
        f"🔗 <a href=\"{claim_url}\">Vào Shopee nhập mã ngay kẻo hết!</a>"
    )

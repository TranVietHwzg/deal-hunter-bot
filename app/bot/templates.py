import re
from typing import Dict, Any, Optional

def get_voucher_shop_scope(voucher: Dict[str, Any]) -> Optional[str]:
    """
    Xác định nguồn / gian hàng áp dụng của voucher:
    - Nếu là voucher shop cụ thể: trả về tên shop / nguồn (ví dụ: 'DareU Official Store').
    - Nếu là toàn ngành / toàn sàn / Shopee Live chung: trả về None (không cần ghi theo yêu cầu).
    """
    shop_name = (voucher.get("shop_name") or "").strip()
    shop_id = (str(voucher.get("shop_id") or "")).strip()
    voucher_type = str(voucher.get("voucher_type") or "").upper()
    category = str(voucher.get("category") or "").lower()
    title = str(voucher.get("title") or "")

    # 1. Nếu có tên shop rõ ràng
    if shop_name and shop_name.lower() not in ["none", "null", "toàn sàn", "toàn ngành", "mọi shop", "all"]:
        return shop_name

    # 2. Nếu là voucher loại SHOP
    if voucher_type == "SHOP":
        # Tìm xem có tên shop trong title không: "Shop DareU: ...", "DareU Official Store"
        m = re.search(r'(?:shop|gian hàng)\s+([a-zA-Z0-9_\s\.\-]+?)(?:\s*[:\-]|\s+giảm|\s+đơn|$)', title, re.IGNORECASE)
        if m:
            found_name = m.group(1).strip()
            if found_name and found_name.lower() not in ["official", "mall", "toàn sàn", "toàn ngành"]:
                return found_name
        if shop_id and shop_id not in ["0", "", "none"]:
            return f"Shop ID {shop_id}"
        return "Gian hàng chỉ định"

    # 3. Các loại toàn ngành / toàn sàn: PLATFORM, CATEGORY, LIVE_VIDEO... không ghi thông tin shop
    return None

def format_hot_voucher_alert(voucher: Dict[str, Any], example_product: Optional[Dict[str, Any]] = None) -> str:
    """
    Mẫu cảnh báo voucher gọn gàng, làm nổi bật mã nhập tay / mã ẩn để chạm sao chép.
    Nếu áp dụng cho shop cụ thể: ghi rõ shop. Nếu toàn ngành / toàn sàn: không ghi.
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

    shop_scope = get_voucher_shop_scope(voucher)
    shop_line = f"🏪 <b>Áp dụng:</b> Chỉ Shop {shop_scope}\n" if shop_scope else ""

    # Định dạng siêu gọn: 5 dòng cốt lõi (chỉ thêm dòng shop nếu áp dụng cho shop cụ thể)
    msg = (
        f"{tag} — <b>[{platform}]</b>\n\n"
        f"🏷 <b>Mã nhập:</b> <code>{code}</code> <i>(chạm để sao chép)</i>\n"
        f"💰 <b>Mức giảm:</b> <b>{discount_str}</b>\n"
        f"🛒 <b>Điều kiện:</b> {min_spend_str} | {category}\n"
        f"{shop_line}"
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
        shop_scope = get_voucher_shop_scope(v)
        shop_note = f" <i>(Chỉ Shop: {shop_scope})</i>" if shop_scope else ""
        vouchers_str += f"• <code>{code}</code>{shop_note}\n"

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
    shop_scope = get_voucher_shop_scope(voucher)
    shop_line = f"🏪 <b>Áp dụng:</b> Chỉ Shop {shop_scope}\n" if shop_scope else ""
    return (
        f"⚡️ <b>[MÃ HỒI SINH - VỪA CÓ LƯỢT]</b>\n\n"
        f"🏷 <b>Mã:</b> <code>{code}</code> <i>(chạm để sao chép)</i>\n"
        f"📦 <b>Ưu đãi:</b> {voucher.get('title')}\n"
        f"{shop_line}"
        f"🔗 <a href=\"{claim_url}\">Vào Shopee nhập mã ngay kẻo hết!</a>"
    )


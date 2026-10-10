from typing import Dict, Any, Optional, List
from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus

def format_currency(val: float) -> str:
    """Định dạng tiền tệ đẹp: 100.000đ"""
    return f"{int(val):,}đ".replace(",", ".")

def format_discount_value(voucher: Voucher) -> str:
    if voucher.discount_type == DiscountType.PERCENT:
        max_str = f" (tối đa {format_currency(voucher.max_discount)})" if voucher.max_discount else ""
        return f"{int(voucher.discount_value)}%{max_str}"
    return format_currency(voucher.discount_value)

def format_scope_display(voucher: Voucher) -> str:
    if voucher.scope_type == ScopeType.SHOP:
        return f"Shop {voucher.shop_name or 'Đã theo dõi'}"
    elif voucher.scope_type == ScopeType.CATEGORY:
        cats = ", ".join(voucher.category_names) if voucher.category_names else "Ngành hàng"
        return f"Ngành hàng ({cats})"
    return "Toàn sàn"

def format_upcoming_known_code(voucher: Voucher) -> str:
    """Mẫu 1: Mã đã có và sắp mở"""
    scope_str = format_scope_display(voucher)
    discount_str = format_discount_value(voucher)
    min_spend_str = format_currency(voucher.min_order_value)
    conf_str = "Cao" if voucher.confidence_score >= 80 else "Trung bình"

    msg = (
        "🔑 <b>MÃ SHOPEE SẮP MỞ</b>\n\n"
        f"<b>Phạm vi:</b> {scope_str}\n"
        f"<b>Mã:</b> <code>{voucher.voucher_code}</code>\n"
        f"<b>Giảm:</b> {discount_str}\n"
        f"<b>Đơn tối thiểu:</b> {min_spend_str}\n"
        f"<b>Hiệu lực:</b> {voucher.start_time} ➔ {voucher.end_time}\n"
        f"<b>Trạng thái:</b> Sắp mở\n"
        f"<b>Nguồn:</b> <a href=\"{voucher.source_url}\">Mở nguồn</a>\n"
        f"<b>Độ tin cậy:</b> {conf_str}\n"
    )
    return msg

def format_upcoming_unknown_code(voucher: Voucher) -> str:
    """Mẫu 2: Chương trình sắp mở nhưng chưa có mã"""
    scope_str = format_scope_display(voucher)

    msg = (
        "📅 <b>SỰ KIỆN SHOPEE SẮP MỞ</b>\n\n"
        f"<b>Phạm vi:</b> {scope_str}\n"
        f"<b>Thời gian dự kiến:</b> {voucher.start_time} ➔ {voucher.end_time}\n"
        "<b>Mã:</b> Chưa công bố\n"
        "<b>Trạng thái:</b> Bot đang theo dõi\n"
        f"<b>Nguồn:</b> <a href=\"{voucher.source_url}\">Mở nguồn</a>\n\n"
        "💡 <i>Bot sẽ báo ngay khi có mã hợp lệ được công bố.</i>"
    )
    return msg

def format_active_voucher(voucher: Voucher) -> str:
    """Mẫu 3: Mã vừa kích hoạt (ACTIVE)"""
    scope_str = format_scope_display(voucher)
    discount_str = format_discount_value(voucher)
    min_spend_str = format_currency(voucher.min_order_value)

    msg = (
        "🔥 <b>MÃ SHOPEE ĐÃ MỞ — NHẬP MÃ NGAY</b>\n\n"
        f"<b>Mã:</b> <code>{voucher.voucher_code}</code>\n"
        f"<b>Giảm:</b> {discount_str}\n"
        f"<b>Đơn tối thiểu:</b> {min_spend_str}\n"
        f"<b>Hết hạn:</b> {voucher.end_time}\n"
        f"<b>Phạm vi:</b> {scope_str}\n"
        f"<b>Nguồn:</b> <a href=\"{voucher.source_url}\">Mở nguồn</a>\n\n"
        "👉 <i>Nhập mã ngay tại bước thanh toán kẻo hết lượt!</i>"
    )
    return msg

def format_countdown_reminder(voucher: Voucher, reminder_type: str) -> str:
    """Mẫu 4: Nhắc nhở hẹn giờ mở mã (T-15m, T-2m)"""
    time_badge = "15 PHÚT" if reminder_type == "REMINDER_15M" else "2 PHÚT"
    scope_str = format_scope_display(voucher)
    discount_str = format_discount_value(voucher)
    min_spend_str = format_currency(voucher.min_order_value)

    msg = (
        f"⏰ <b>NHẮC NHỞ: CÒN {time_badge} NỮA MỞ MÃ!</b>\n\n"
        f"<b>Mã:</b> <code>{voucher.voucher_code}</code>\n"
        f"<b>Giảm:</b> {discount_str}\n"
        f"<b>Đơn tối thiểu:</b> {min_spend_str}\n"
        f"<b>Giờ mở:</b> {voucher.start_time}\n"
        f"<b>Phạm vi:</b> {scope_str}\n\n"
        "💡 <i>Hãy chuẩn bị sẵn đơn hàng trong giỏ để áp mã kịp thời!</i>"
    )
    return msg

def format_code_revealed(voucher: Voucher) -> str:
    """Mẫu 5: Sự kiện vừa lộ mã thật"""
    scope_str = format_scope_display(voucher)
    discount_str = format_discount_value(voucher)
    min_spend_str = format_currency(voucher.min_order_value)

    msg = (
        "🎉 <b>ĐÃ CÔNG BỐ MÃ: SỰ KIỆN SHOPEE</b>\n\n"
        f"<b>Mã chính thức:</b> <code>{voucher.voucher_code}</code>\n"
        f"<b>Phạm vi:</b> {scope_str}\n"
        f"<b>Giảm:</b> {discount_str}\n"
        f"<b>Đơn tối thiểu:</b> {min_spend_str}\n"
        f"<b>Hiệu lực:</b> {voucher.start_time} ➔ {voucher.end_time}\n"
        f"<b>Nguồn:</b> <a href=\"{voucher.source_url}\">Mở nguồn</a>\n"
    )
    return msg

def format_scan_summary(scan_res: Dict[str, Any], upcoming_count: int = 0) -> str:
    """Mẫu 6: Kết quả sau khi bấm 'Quét ngay'"""
    items_scanned = scan_res.get("items_scanned", 0)
    new_v = scan_res.get("new_vouchers", 0)
    updated_v = scan_res.get("updated_vouchers", 0)

    if new_v == 0 and updated_v == 0:
        return "⚡ <b>Không phát hiện mã giảm giá mới.</b>\n<i>Kho mã của bạn hiện đã được đồng bộ mới nhất.</i>"

    msg = (
        "✅ <b>HOÀN TẤT CHU KỲ QUÉT SHOPEE</b>\n"
        "────────────────────\n"
        f"• Nguồn đã quét: Shopee Campaigns & Tracked Shops\n"
        f"• Mục kiểm tra: {items_scanned}\n"
        f"• Mã mới phát hiện: <b>{new_v}</b>\n"
        f"• Mã cập nhật/lộ mã: <b>{updated_v}</b>\n"
        f"• Mã sắp mở đang theo dõi: <b>{upcoming_count}</b>\n"
    )
    return msg

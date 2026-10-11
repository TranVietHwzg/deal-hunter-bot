from typing import Dict, Any, Optional
from models.voucher import Voucher, ScopeType, DiscountType

def format_currency(val: float) -> str:
    return f"{int(val):,}đ".replace(",", ".")

def format_discount_display(voucher: Voucher) -> str:
    if voucher.discount_type == DiscountType.PERCENT:
        max_str = f" tối đa {format_currency(voucher.max_discount)}" if voucher.max_discount else ""
        return f"{int(voucher.discount_value)}%{max_str}"
    return format_currency(voucher.discount_value)

def format_scope_display(voucher: Voucher) -> str:
    if voucher.scope_type == ScopeType.SHOP:
        return f"Shop {voucher.shop_name or 'Đã theo dõi'}"
    elif voucher.scope_type == ScopeType.CATEGORY:
        cats = ", ".join(voucher.category_names) if voucher.category_names else "Ngành hàng"
        return f"Ngành hàng ({cats})"
    return "Toàn sàn"

def format_elite_upcoming_known(voucher: Voucher, score: int = 90, reason: str = "") -> str:
    """Mẫu 1: Voucher SIÊU XỊN sắp mở"""
    discount_str = format_discount_display(voucher)
    min_spend_str = format_currency(voucher.min_order_value)
    scope_str = format_scope_display(voucher)
    
    if voucher.voucher_code:
        code_line = f"<b>Mã nhập tay:</b> <code>{voucher.voucher_code}</code> <i>(Chạm để sao chép)</i>\n"
    else:
        code_line = "<b>Hình thức:</b> 🎟️ Lưu trên banner Shopee <i>(Không cần nhập code)</i>\n"

    if not reason:
        reason = "Giảm cao, đơn hợp lý, phạm vi rộng, nguồn xác minh."

    return (
        "🔥 <b>MÃ SHOPEE SIÊU XỊN — SẮP MỞ</b>\n\n"
        f"{code_line}"
        f"<b>Giảm:</b> {discount_str}\n"
        f"<b>Đơn tối thiểu:</b> {min_spend_str}\n"
        f"<b>Phạm vi:</b> {scope_str}\n"
        f"<b>Hiệu lực:</b> {voucher.start_time} ➔ {voucher.end_time}\n"
        f"<b>Điểm Elite:</b> {score}/100\n"
        f"<b>Lý do:</b> {reason}\n"
    )

def format_elite_shop_voucher(voucher: Voucher, score: int = 90, reason: str = "") -> str:
    """Mẫu 2: Voucher shop SIÊU XỊN"""
    shop_str = voucher.shop_name or "Shop đang theo dõi"
    discount_str = format_discount_display(voucher)
    min_spend_str = format_currency(voucher.min_order_value)

    if voucher.voucher_code:
        code_line = f"<b>Mã nhập tay:</b> <code>{voucher.voucher_code}</code> <i>(Chạm để sao chép)</i>\n"
    else:
        code_line = "<b>Hình thức:</b> 🎟️ Lưu tại trang gian hàng <i>(Không cần nhập code)</i>\n"

    if not reason:
        reason = f"Tiết kiệm thực tế cao, shop đang theo dõi."

    return (
        "🔥 <b>MÃ SHOP SIÊU XỊN</b>\n\n"
        f"<b>Shop:</b> {shop_str}\n"
        f"{code_line}"
        f"<b>Giảm:</b> {discount_str}\n"
        f"<b>Đơn tối thiểu:</b> {min_spend_str}\n"
        f"<b>Hiệu lực:</b> {voucher.start_time} ➔ {voucher.end_time}\n"
        f"<b>Điểm Elite:</b> {score}/100\n"
        f"<b>Lý do:</b> {reason}\n"
    )

def format_elite_code_revealed(voucher: Voucher, score: int = 90) -> str:
    """Mẫu 3: Mã được công bố sau khi theo dõi sự kiện"""
    code_str = voucher.voucher_code or "CHƯA CÔNG BỐ"
    discount_str = format_discount_display(voucher)
    min_spend_str = format_currency(voucher.min_order_value)

    return (
        "🔑 <b>MÃ SẮP MỞ ĐÃ LỘ CODE</b>\n\n"
        "<i>Sự kiện đã được theo dõi trước đó.</i>\n"
        f"<b>Mã:</b> <code>{code_str}</code>\n"
        f"<b>Giảm:</b> {discount_str}\n"
        f"<b>Đơn tối thiểu:</b> {min_spend_str}\n"
        f"<b>Hiệu lực:</b> {voucher.start_time} ➔ {voucher.end_time}\n"
        f"<b>Điểm Elite:</b> {score}/100\n"
    )

def format_scan_summary_elite(
    sources_count: int,
    items_scanned: int,
    items_rejected: int,
    elite_new: int,
    elite_updated: int,
    elite_upcoming: int
) -> str:
    """Bảng kết quả sau khi bấm Quét ngay chuẩn Section 9"""
    return (
        "<b>Đã quét xong.</b>\n\n"
        f"• <b>Nguồn đã quét:</b> {sources_count}\n"
        f"• <b>Voucher phát hiện:</b> {items_scanned}\n"
        f"• <b>Voucher bị loại:</b> {items_rejected}\n"
        f"• <b>Voucher Elite mới:</b> {elite_new}\n"
        f"• <b>Voucher Elite được cập nhật:</b> {elite_updated}\n"
        f"• <b>Voucher sắp mở:</b> {elite_upcoming}"
    )

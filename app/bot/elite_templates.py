from typing import Dict, Any, Optional, Tuple, List
from models.voucher import Voucher, ScopeType, DiscountType, VerificationStatus, VoucherStatus

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

def format_verified_active_voucher(voucher: Voucher) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Định dạng chuẩn: 🔥 VOUCHER ELITE ĐÃ XÁC MINH"""
    source_label = voucher.source_title or voucher.source_type
    shop_line = f"<b>Shop:</b> {voucher.shop_name}\n" if voucher.shop_name else ""
    confidence_label = "Cao" if voucher.confidence_score >= 85 else "Trung bình"
    last_check = voucher.last_checked_at[:16].replace("T", " ") if voucher.last_checked_at else "Vừa kiểm tra"

    msg = (
        "🔥 <b>VOUCHER ELITE ĐÃ XÁC MINH</b>\n\n"
        f"<b>Mã:</b> <code>{voucher.voucher_code}</code> <i>(Chạm để sao chép)</i>\n"
        "<b>Trạng thái:</b> ✅ Đang hoạt động\n"
        f"<b>Xác minh:</b> <code>{voucher.verification_status.value if isinstance(voucher.verification_status, VerificationStatus) else voucher.verification_status}</code>\n"
        f"<b>Nguồn:</b> {source_label}\n"
        f"<b>Phạm vi:</b> {format_scope_display(voucher)}\n"
        f"{shop_line}"
        f"<b>Giảm:</b> {format_discount_display(voucher)}\n"
        f"<b>Đơn tối thiểu:</b> {format_currency(voucher.min_order_value)}\n"
        f"<b>Hiệu lực:</b> {voucher.start_time} → {voucher.end_time}\n"
        f"<b>Kiểm tra lần cuối:</b> {last_check}\n"
        f"<b>Độ tin cậy:</b> {confidence_label}\n"
    )

    markup = None
    if voucher.source_url:
        markup = {
            "inline_keyboard": [
                [{"text": "🔗 Mở nguồn xác minh", "url": voucher.source_url}]
            ]
        }
    return msg, markup

def format_verified_upcoming_voucher(voucher: Voucher) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Định dạng chuẩn: 🔑 VOUCHER ELITE SẮP MỞ"""
    source_label = voucher.source_title or voucher.source_type
    last_check = voucher.last_checked_at[:16].replace("T", " ") if voucher.last_checked_at else "Vừa kiểm tra"

    msg = (
        "🔑 <b>VOUCHER ELITE SẮP MỞ</b>\n\n"
        f"<b>Mã:</b> <code>{voucher.voucher_code}</code> <i>(Chạm để sao chép)</i>\n"
        "<b>Trạng thái:</b> ⏳ Sắp mở\n"
        f"<b>Xác minh:</b> <code>{voucher.verification_status.value if isinstance(voucher.verification_status, VerificationStatus) else voucher.verification_status}</code>\n"
        f"<b>Nguồn:</b> {source_label}\n"
        f"<b>Phạm vi:</b> {format_scope_display(voucher)}\n"
        f"<b>Giảm:</b> {format_discount_display(voucher)}\n"
        f"<b>Đơn tối thiểu:</b> {format_currency(voucher.min_order_value)}\n"
        f"<b>Hiệu lực:</b> {voucher.start_time} → {voucher.end_time}\n"
        f"<b>Kiểm tra lần cuối:</b> {last_check}\n"
    )

    markup = None
    if voucher.source_url:
        markup = {
            "inline_keyboard": [
                [{"text": "🔗 Mở nguồn sắp mở", "url": voucher.source_url}]
            ]
        }
    return msg, markup

def format_upcoming_unknown_event(voucher: Voucher) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Định dạng chuẩn: 📅 SỰ KIỆN ĐANG THEO DÕI (Chưa có mã)"""
    source_label = voucher.source_title or voucher.source_url
    msg = (
        "📅 <b>SỰ KIỆN ĐANG THEO DÕI</b>\n\n"
        f"<b>Sự kiện:</b> {voucher.title}\n"
        "<b>Mã:</b> Chưa công bố\n"
        "<b>Trạng thái:</b> <code>UPCOMING_UNKNOWN_CODE</code>\n"
        f"<b>Nguồn:</b> {source_label}\n"
        f"<b>Dự kiến bắt đầu:</b> {voucher.start_time}\n"
        f"<b>Mức giảm dự kiến:</b> {format_discount_display(voucher)} (Đơn {format_currency(voucher.min_order_value)})\n\n"
        "ℹ️ <i>Lưu ý: Chưa phải voucher xác minh; bot sẽ chỉ báo khi có mã thật.</i>"
    )
    markup = None
    if voucher.source_url:
        markup = {
            "inline_keyboard": [
                [{"text": "🔗 Xem trang sự kiện", "url": voucher.source_url}]
            ]
        }
    return msg, markup

def format_voucher_verification_card(voucher: Voucher) -> str:
    """Trả thông tin kiểm chứng đầy đủ cho lệnh /verify <code_name>"""
    vs = voucher.verification_status.value if isinstance(voucher.verification_status, VerificationStatus) else voucher.verification_status
    shop_info = f"• Shop ID: <code>{voucher.shop_id}</code> | Shop: <b>{voucher.shop_name}</b>\n" if voucher.shop_id else ""
    return (
        f"📋 <b>KẾT QUẢ KIỂM TOÁN VOUCHER: <code>{voucher.voucher_code or voucher.id}</code></b>\n"
        "────────────────────\n"
        f"• <b>Trạng thái xác minh:</b> <code>{vs}</code>\n"
        f"• <b>Trạng thái vận hành:</b> {voucher.status.value if isinstance(voucher.status, VoucherStatus) else voucher.status}\n"
        f"• <b>Nguồn gốc:</b> {voucher.source_type} ({voucher.source_title or 'Chưa rõ'})\n"
        f"• <b>URL nguồn:</b> {voucher.source_url}\n"
        f"• <b>Thời điểm thu thập:</b> {voucher.source_captured_at or voucher.created_at or 'N/A'}\n"
        f"• <b>Bằng chứng trích xuất:</b> <i>{voucher.source_evidence_excerpt or 'Chưa có trích đoạn văn bản'}</i>\n"
        f"• <b>Phạm vi:</b> {format_scope_display(voucher)}\n"
        f"{shop_info}"
        f"• <b>Mức giảm:</b> {format_discount_display(voucher)}\n"
        f"• <b>Đơn tối thiểu:</b> {format_currency(voucher.min_order_value)}\n"
        f"• <b>Thời gian hiệu lực:</b> {voucher.start_time} → {voucher.end_time}\n"
        f"• <b>Múi giờ:</b> {voucher.timezone}\n"
        f"• <b>Xác minh lúc:</b> {voucher.verified_at or 'Chưa xác minh'}\n"
        f"• <b>Kiểm tra lần cuối:</b> {voucher.last_checked_at or 'N/A'}\n"
    )

def format_voucher_source_card(voucher: Voucher) -> str:
    """Trả thông tin nguồn cho lệnh /source <code_name>"""
    shop_line = f"• Shop: <b>{voucher.shop_name}</b> ({voucher.shop_url or 'N/A'})\n" if voucher.shop_name else ""
    return (
        f"🔎 <b>THÔNG TIN NGUỒN GỐC MÃ: <code>{voucher.voucher_code or voucher.id}</code></b>\n"
        "────────────────────\n"
        f"• Nền tảng: <b>{voucher.platform}</b>\n"
        f"• Loại nguồn: <b>{voucher.source_type}</b>\n"
        f"• Tiêu đề nguồn: <b>{voucher.source_title or 'N/A'}</b>\n"
        f"• URL gốc: {voucher.source_url}\n"
        f"{shop_line}"
        f"• Thu thập lúc: <code>{voucher.source_captured_at or 'N/A'}</code>\n"
        f"• Trích dẫn bằng chứng: <i>{voucher.source_evidence_excerpt or 'N/A'}</i>\n"
    )

def format_voucher_status_card(voucher: Voucher) -> str:
    """Trả trạng thái thực tế cho lệnh /status <code_name>"""
    vs = voucher.verification_status.value if isinstance(voucher.verification_status, VerificationStatus) else voucher.verification_status
    return (
        f"📊 <b>TRẠNG THÁI THỰC TẾ: <code>{voucher.voucher_code or voucher.id}</code></b>\n"
        "────────────────────\n"
        f"• Verification Status: <b>{vs}</b>\n"
        f"• Operational Status: <b>{voucher.status.value if isinstance(voucher.status, VoucherStatus) else voucher.status}</b>\n"
        f"• Thời gian áp dụng: <b>{voucher.start_time} → {voucher.end_time}</b>\n"
        f"• Kiểm tra lần cuối: <b>{voucher.last_checked_at or 'N/A'}</b>\n"
    )

def format_audit_summary_report(summary: Dict[str, int]) -> str:
    """Trả báo cáo kiểm toán cho lệnh /audit"""
    return (
        "📊 <b>BÁO CÁO KIỂM TOÁN TÍNH THẬT CỦA VOUCHER</b>\n"
        "────────────────────\n"
        f"• ✅ <b>Đã xác minh đang chạy (VERIFIED_ACTIVE):</b> {summary.get('VERIFIED_ACTIVE', 0)}\n"
        f"• ⏳ <b>Đã xác minh sắp mở (VERIFIED_UPCOMING):</b> {summary.get('VERIFIED_UPCOMING', 0)}\n"
        f"• 📅 <b>Sự kiện chưa lộ code (UPCOMING_UNKNOWN_CODE):</b> {summary.get('UPCOMING_UNKNOWN_CODE', 0)}\n"
        f"• 👤 <b>Cần ví cá nhân (PERSONAL_ELIGIBILITY_UNKNOWN):</b> {summary.get('PERSONAL_ELIGIBILITY_UNKNOWN', 0)}\n"
        f"• ⚠️ <b>Chờ kiểm tra (UNVERIFIED):</b> {summary.get('UNVERIFIED', 0)}\n"
        f"• ❌ <b>Sai/Hết hạn/Loại bỏ (INVALID):</b> {summary.get('INVALID', 0)}\n"
        f"• 🚫 <b>Dữ liệu mẫu/mock (TEST_DATA):</b> {summary.get('TEST_DATA', 0)}\n"
        "────────────────────\n"
        f"• <b>TỔNG CỘNG TRONG RADAR:</b> {summary.get('TOTAL', 0)}\n\n"
        "🛡️ <i>Quy tắc: Chỉ VERIFIED_ACTIVE và VERIFIED_UPCOMING mới được xuất hiện trên Elite Radar và gửi Telegram!</i>"
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
        f"• <b>Voucher Elite cập nhật:</b> {elite_updated}\n"
        f"• <b>Voucher Elite sắp mở:</b> {elite_upcoming}\n\n"
        "🚫 <i>Đã áp dụng bộ lọc 100% Zero Freeship & Zero Fake Codes.</i>"
    )

def format_elite_shop_voucher(voucher: Voucher, score: int = 90, reason: str = "") -> str:
    shop_title = voucher.shop_name or f"Shop ID {voucher.shop_id}"
    code_str = voucher.voucher_code or "ÁP MÃ TẠI SHOP"
    reason_line = f"<b>Lý do đạt:</b> {reason}\n" if reason else ""
    return (
        "🏪 <b>MÃ SHOP SIÊU XỊN — ĐÃ THEO DÕI</b>\n\n"
        f"<b>Shop:</b> {shop_title}\n"
        f"<b>Mã:</b> <code>{code_str}</code>\n"
        f"<b>Giảm:</b> {format_discount_display(voucher)}\n"
        f"<b>Đơn tối thiểu:</b> {format_currency(voucher.min_order_value)}\n"
        f"<b>Hiệu lực:</b> {voucher.start_time} → {voucher.end_time}\n"
        f"<b>Điểm Elite:</b> {score}/100\n"
        f"{reason_line}"
        "👉 <i>Vào ngay gian hàng để lưu và dùng mã!</i>\n"
    )

def format_elite_upcoming_known(voucher: Voucher, score: int = 90, reason: str = "") -> str:
    code_str = voucher.voucher_code or "Chưa công bố"
    reason_line = f"<b>Lý do đạt:</b> {reason}\n" if reason else ""
    return (
        "🔑 <b>MÃ SẮP MỞ ĐÃ LỘ CODE</b>\n\n"
        f"<b>Mã:</b> <code>{code_str}</code>\n"
        f"<b>Giảm:</b> {format_discount_display(voucher)}\n"
        f"<b>Đơn tối thiểu:</b> {format_currency(voucher.min_order_value)}\n"
        f"<b>Phạm vi:</b> {format_scope_display(voucher)}\n"
        f"<b>Mở lúc:</b> {voucher.start_time}\n"
        f"<b>Hết hạn:</b> {voucher.end_time}\n"
        f"<b>Điểm Elite:</b> {score}/100\n"
        f"{reason_line}"
        "⏰ <i>Bot sẽ tự động nhắc bạn trước giờ mở!</i>\n"
    )

def format_elite_code_revealed(voucher: Voucher, score: int = 90) -> str:
    code_str = voucher.voucher_code or "Chưa rõ"
    return (
        "🔑 <b>MÃ SẮP MỞ ĐÃ LỘ CODE</b>\n\n"
        f"<b>Mã:</b> <code>{code_str}</code>\n"
        f"<b>Giảm:</b> {format_discount_display(voucher)}\n"
        f"<b>Đơn tối thiểu:</b> {format_currency(voucher.min_order_value)}\n"
        f"<b>Phạm vi:</b> {format_scope_display(voucher)}\n"
        f"<b>Hiệu lực:</b> {voucher.start_time} → {voucher.end_time}\n"
        f"<b>Điểm Elite:</b> {score}/100\n"
        "👉 <i>Lưu mã ngay trước khi số lượng đạt giới hạn!</i>\n"
    )

def format_coverage_report(stats: Dict[str, Any], tracked_count: int = 0) -> str:
    cookie_status = "✅ <b>ĐÃ KẾT NỐI</b> (Sẵn sàng vượt Akamai 403)" if stats.get("cookie_enabled") else "⚠️ <b>CHƯA CẤU HÌNH</b> (Khuyên dùng: nạp SHOPEE_COOKIE để mở khóa 100% API)"
    return (
        "📡 <b>BÁO CÁO ĐỘ BAO PHỦ DỮ LIỆU (ANTI-MISS RADAR)</b>\n"
        "────────────────────\n"
        f"• <b>Shopee Session Cookie:</b> {cookie_status}\n"
        f"• <b>Hub cộng đồng & RSC:</b> ✅ Hoạt động (bloggiamgia.vn)\n"
        f"• <b>Gian hàng theo dõi (/shops):</b> {tracked_count} shop đang quét\n"
        f"• <b>Chiến dịch toàn sàn & Khung giờ:</b> ✅ Đang theo dõi\n"
        "────────────────────\n"
        "🛡️ <b>Cam kết:</b> 100% Zero Freeship & Zero Fake Codes.\n"
        "💡 <i>Mẹo: Thêm các shop bạn muốn săn bằng lệnh <code>/shops add &lt;link_shop&gt;</code>!</i>"
    )



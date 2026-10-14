from models.voucher import Voucher, ScopeType, VoucherStatus
from services.dedupe_service import DedupeService
from core.voucher_lifecycle import parse_vietnam_time, VN_TZ
from datetime import datetime
from app.bot.elite_templates import (
    format_elite_upcoming_known,
    format_elite_shop_voucher,
    format_elite_code_revealed,
    format_upcoming_unknown_event,
    format_discount_display,
    format_currency,
    format_scope_display
)
from app.bot.elite_keyboard import get_elite_voucher_action_keyboard

from config.settings import settings

class EliteNotificationService:
    """Quản lý phát thông báo Elite Voucher lên Telegram:
    - Kiểm duyệt nghiêm ngặt: điểm < 70 tuyệt đối không gửi (Mã 30k/0đ đạt 78đ được duyệt)
    - Chống trùng Fingerprint qua DedupeService
    - Chốt chặn Expiry-Guard: Tuyệt đối không gửi voucher hết hạn
    - Gửi thông báo mẫu chuẩn theo Section 10
    """
    def __init__(self, telegram_bot_service, scan_repo=None, dedupe_service=None):
        self.bot = telegram_bot_service
        self.scan_repo = scan_repo
        self.dedupe = dedupe_service or DedupeService(scan_repo=scan_repo)

    async def notify_elite_voucher(
        self,
        voucher: Voucher,
        event_type: str,
        score: int = 90,
        reason: str = ""
    ) -> bool:
        # 1. Expiry-Guard: Tuyệt đối không gửi thông báo cho voucher đã hết hạn hoặc đã hủy
        if voucher.status in (VoucherStatus.EXPIRED, VoucherStatus.CANCELLED):
            return False
        end_dt = parse_vietnam_time(voucher.end_time)
        now = datetime.now(VN_TZ)
        from datetime import timedelta
        if end_dt and (now - end_dt) > timedelta(hours=48):
            return False

        # 2. Ngưỡng bắt buộc: Điểm dưới 70 không gửi Telegram (>=70 là ĐÁNG LẤY, >=80 là SIÊU XỊN)
        min_notify = getattr(settings, "min_alert_threshold", 70)
        if score < min_notify:
            return False

        # 3. Chống trùng fingerprint qua DedupeService
        fp = self.dedupe.calculate_fingerprint(voucher, event_type)
        if self.dedupe.is_duplicate(fp):
            return False

        # Định dạng nội dung theo mẫu Section 10
        shop_target_url = getattr(voucher, "shop_url", None)
        if event_type == "CODE_REVEALED":
            text = format_elite_code_revealed(voucher, score=score)
            markup = get_elite_voucher_action_keyboard(source_url=voucher.source_url, shop_url=shop_target_url)
        elif voucher.scope_type == ScopeType.SHOP:
            text = format_elite_shop_voucher(voucher, score=score, reason=reason)
            markup = get_elite_voucher_action_keyboard(source_url=voucher.source_url, shop_url=shop_target_url)
        elif event_type in ("UPCOMING_UNKNOWN", "WATCH"):
            text, t_markup = format_upcoming_unknown_event(voucher)
            markup = t_markup or get_elite_voucher_action_keyboard(source_url=voucher.source_url, shop_url=shop_target_url)
        elif event_type in ("UPCOMING_KNOWN", "UPCOMING"):
            text = format_elite_upcoming_known(voucher, score=score, reason=reason)
            markup = get_elite_voucher_action_keyboard(source_url=voucher.source_url, shop_url=shop_target_url)
        else:
            # Voucher ACTIVE
            from app.bot.elite_templates import format_code_block
            text = (
                "🔥 <b>MÃ SHOPEE SIÊU XỊN — ĐANG HOẠT ĐỘNG</b>\n\n"
                f"{format_code_block(voucher)}\n"
                f"<b>Giảm:</b> {format_discount_display(voucher)}\n"
                f"<b>Đơn tối thiểu:</b> {format_currency(voucher.min_order_value)}\n"
                f"<b>Phạm vi:</b> {format_scope_display(voucher)}\n"
                f"<b>Hết hạn:</b> {voucher.end_time}\n"
                f"<b>Điểm Elite:</b> {score}/100\n"
                "👉 <i>Nhập mã ngay tại giỏ hàng kẻo hết lượt!</i>\n"
            )
            markup = get_elite_voucher_action_keyboard(source_url=voucher.source_url, shop_url=shop_target_url)

        if self.bot and hasattr(self.bot, "send_message"):
            await self.bot.send_message(text, reply_markup=markup)

        self.dedupe.record_sent(fp, voucher.id, event_type)
        return True

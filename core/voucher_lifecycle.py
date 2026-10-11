import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any
from models.voucher import Voucher, VoucherStatus

VN_TZ = timezone(timedelta(hours=7))

def parse_vietnam_time(time_str: str) -> Optional[datetime]:
    """
    Parse chuỗi thời gian thành datetime có múi giờ Asia/Ho_Chi_Minh (+07:00).
    Hỗ trợ ISO-8601, 'YYYY-MM-DD HH:MM:SS', 'HH:MM DD/MM/YYYY', hoặc 'HH:MM ngày DD/MM'.
    """
    if not time_str:
        return None
    time_str = str(time_str).strip()

    # 1. ISO format
    try:
        dt = datetime.fromisoformat(time_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=VN_TZ)
        return dt.astimezone(VN_TZ)
    except Exception:
        pass

    # 2. 'HH:MM DD/MM/YYYY' hoặc 'HH:MM DD/MM'
    m_full = re.search(r'(\d{1,2}):(\d{2})(?:\s*ngày)?\s+(\d{1,2})/(\d{1,2})(?:/(\d{4}))?', time_str)
    if m_full:
        hour = int(m_full.group(1))
        minute = int(m_full.group(2))
        day = int(m_full.group(3))
        month = int(m_full.group(4))
        year = int(m_full.group(5)) if m_full.group(5) else datetime.now(VN_TZ).year
        try:
            return datetime(year, month, day, hour, minute, tzinfo=VN_TZ)
        except ValueError:
            pass

    # 3. 'YYYY-MM-DD HH:MM'
    m_iso = re.search(r'(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})', time_str)
    if m_iso:
        y, m, d, h, mn = map(int, m_iso.groups())
        try:
            return datetime(y, m, d, h, mn, tzinfo=VN_TZ)
        except ValueError:
            pass

    return None

def determine_initial_status(
    voucher_code: Optional[str],
    start_time_str: str,
    end_time_str: str,
    confidence_score: int = 90
) -> VoucherStatus:
    """Xác định trạng thái ban đầu của voucher khi mới thu thập"""
    if confidence_score < 50:
        return VoucherStatus.UNVERIFIED

    now = datetime.now(VN_TZ)
    start_dt = parse_vietnam_time(start_time_str)
    end_dt = parse_vietnam_time(end_time_str)

    if end_dt and now > end_dt:
        return VoucherStatus.EXPIRED

    if start_dt and start_dt > now:
        if voucher_code and voucher_code.strip():
            return VoucherStatus.UPCOMING_CODE_KNOWN
        else:
            return VoucherStatus.UPCOMING_UNKNOWN_CODE

    if voucher_code and voucher_code.strip():
        return VoucherStatus.ACTIVE

    return VoucherStatus.DISCOVERED

def evaluate_lifecycle_transition(voucher: Voucher) -> Tuple[Optional[VoucherStatus], Optional[str]]:
    """
    Đánh giá chuyển trạng thái của voucher theo thời gian thực (Asia/Ho_Chi_Minh).
    Trả về (new_status, event_name). Nếu không chuyển trạng thái, new_status là None.
    """
    now = datetime.now(VN_TZ)
    start_dt = parse_vietnam_time(voucher.start_time)
    end_dt = parse_vietnam_time(voucher.end_time)

    # 1. Hết hạn (EXPIRED)
    if end_dt and now > end_dt and voucher.status not in (VoucherStatus.EXPIRED, VoucherStatus.CANCELLED):
        return VoucherStatus.EXPIRED, "VOUCHER_EXPIRED"

    # 2. Đến giờ mở mã (UPCOMING_CODE_KNOWN -> ACTIVE)
    if voucher.status == VoucherStatus.UPCOMING_CODE_KNOWN:
        if start_dt and now >= start_dt:
            if not end_dt or now <= end_dt:
                return VoucherStatus.ACTIVE, "VOUCHER_OPENED"

    # 3. Đã có code từ UPCOMING_UNKNOWN_CODE
    if voucher.status == VoucherStatus.UPCOMING_UNKNOWN_CODE and voucher.voucher_code:
        if start_dt and start_dt > now:
            return VoucherStatus.UPCOMING_CODE_KNOWN, "CODE_REVEALED"
        elif not end_dt or now <= end_dt:
            return VoucherStatus.ACTIVE, "VOUCHER_OPENED"

    return None, None

def check_upcoming_reminder(voucher: Voucher, elite_score: Optional[int] = None) -> Optional[str]:
    """
    Kiểm tra xem voucher sắp mở có cần gửi nhắc nhở không.
    Theo chuẩn Elite: Chỉ gửi nhắc T-15m và T-2m cho voucher SIÊU XỊN (90–100 điểm).
    """
    if voucher.status != VoucherStatus.UPCOMING_CODE_KNOWN or not voucher.voucher_code:
        return None

    if elite_score is not None and elite_score < 90:
        return None

    now = datetime.now(VN_TZ)
    start_dt = parse_vietnam_time(voucher.start_time)
    if not start_dt:
        return None

    diff_seconds = (start_dt - now).total_seconds()
    if 2 * 60 < diff_seconds <= 15 * 60:
        return "REMINDER_15M"
    elif 0 < diff_seconds <= 2 * 60:
        return "REMINDER_2M"

    return None

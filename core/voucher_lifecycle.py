import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple, Dict, Any
from models.voucher import Voucher, VoucherStatus
from config.settings import settings

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
        year_provided = bool(m_full.group(5))
        year = int(m_full.group(5)) if year_provided else datetime.now(VN_TZ).year
        try:
            res_dt = datetime(year, month, day, hour, minute, tzinfo=VN_TZ)
            # Nếu năm không được cung cấp và thời gian rơi vào quá khứ quá 7 ngày,
            # tự động cộng thêm 1 năm (chuyển giao năm mới)
            if not year_provided and res_dt < (datetime.now(VN_TZ) - timedelta(days=7)):
                res_dt = res_dt.replace(year=year + 1)
            return res_dt
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
    confidence_score: int = 90,
    claim_type: str = "CODE"
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

    if claim_type == "SAVE_BUTTON":
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

    # 1. Hết hạn (EXPIRED) hoặc không hợp lệ (INVALID)
    v_stat = voucher.verification_status.value if hasattr(voucher.verification_status, "value") else str(voucher.verification_status)
    if (end_dt and now > end_dt) or v_stat == "INVALID":
        if voucher.status not in (VoucherStatus.EXPIRED, VoucherStatus.CANCELLED):
            return VoucherStatus.EXPIRED, "VOUCHER_EXPIRED"

    # 2. Khôi phục từ EXHAUSTED sang ACTIVE nếu còn hạn và percentage_used < 90%
    if voucher.status == VoucherStatus.EXHAUSTED:
        if voucher.percentage_used is not None and voucher.percentage_used < 90.0:
            if not end_dt or now <= end_dt:
                return VoucherStatus.ACTIVE, "VOUCHER_RESTOCKED"

    # 3. Chuyển sang EXHAUSTED nếu đã dùng >= 90% (trên Shopee 90% là thực tế đã hết lượt)
    if voucher.status == VoucherStatus.ACTIVE:
        if voucher.percentage_used is not None and voucher.percentage_used >= 90.0:
            return VoucherStatus.EXHAUSTED, "VOUCHER_EXHAUSTED"

    # 3b. Heuristic Flash Expiration (TTL) cho mã Hot / Giảm sâu:
    # Mã giảm >=30k đơn 0đ, >=30%, hoặc >=100k có ngân sách giới hạn
    if voucher.status == VoucherStatus.ACTIVE:
        dtype_str = voucher.discount_type.value if hasattr(voucher.discount_type, "value") else str(voucher.discount_type)
        is_flash_deal = (
            (dtype_str == "PERCENT" and voucher.discount_value >= 30.0) or
            (dtype_str == "FIXED" and voucher.discount_value >= 30000.0 and voucher.min_order_value == 0.0) or
            (voucher.discount_value >= 100000.0)
        )
        if is_flash_deal and start_dt:
            age_seconds = (now - start_dt).total_seconds()
            # Nếu đợt mở mã đã diễn ra hơn 24 giờ trước mà không có cập nhật restock -> hết lượt
            if age_seconds >= 24 * 3600:
                return VoucherStatus.EXHAUSTED, "VOUCHER_EXHAUSTED"
            # Nếu đợt mở mã đã diễn ra hơn 3 giờ trước và không có tín hiệu mới -> hết lượt
            elif age_seconds >= 3 * 3600:
                last_time_str = voucher.last_checked_at or voucher.last_seen_at or voucher.source_captured_at
                is_stale = True
                if last_time_str:
                    try:
                        last_dt = datetime.fromisoformat(str(last_time_str).replace("Z", "+00:00"))
                        if (datetime.now(timezone.utc) - last_dt).total_seconds() < 3 * 3600:
                            is_stale = False
                    except Exception:
                        pass
                if is_stale:
                    return VoucherStatus.EXHAUSTED, "VOUCHER_EXHAUSTED"

    # 4. Đến giờ mở mã (UPCOMING_CODE_KNOWN -> ACTIVE)
    if voucher.status == VoucherStatus.UPCOMING_CODE_KNOWN:
        if start_dt and now >= start_dt:
            if not end_dt or now <= end_dt:
                return VoucherStatus.ACTIVE, "VOUCHER_OPENED"

    # 5. Đã có code từ UPCOMING_UNKNOWN_CODE
    if voucher.status == VoucherStatus.UPCOMING_UNKNOWN_CODE and voucher.voucher_code:
        if start_dt and start_dt > now:
            return VoucherStatus.UPCOMING_CODE_KNOWN, "CODE_REVEALED"
        elif not end_dt or now <= end_dt:
            return VoucherStatus.ACTIVE, "VOUCHER_OPENED"

    # 6. Voucher từ DISCOVERED có mã hoặc là SAVE_BUTTON
    if voucher.status == VoucherStatus.DISCOVERED:
        if voucher.voucher_code or getattr(voucher, "claim_type", "") == "SAVE_BUTTON":
            if start_dt and start_dt > now:
                return (VoucherStatus.UPCOMING_CODE_KNOWN if voucher.voucher_code else VoucherStatus.UPCOMING_UNKNOWN_CODE), "UPCOMING_DISCOVERED"
            elif not end_dt or now <= end_dt:
                return VoucherStatus.ACTIVE, "VOUCHER_OPENED"

    return None, None

def check_upcoming_reminder(voucher: Voucher, elite_score: Optional[int] = None) -> Optional[str]:
    """
    Kiểm tra xem voucher sắp mở có cần gửi nhắc nhở không.
    Hỗ trợ cả UPCOMING_CODE_KNOWN và UPCOMING_UNKNOWN_CODE cho các mốc T-24h, T-15m, T-2m.
    Chỉ gửi cho voucher đạt ngưỡng điểm thông báo (mặc định >= 70 điểm).
    """
    raw_status = voucher.status.value if isinstance(voucher.status, VoucherStatus) else str(voucher.status)
    if raw_status not in ("UPCOMING_CODE_KNOWN", "UPCOMING_UNKNOWN_CODE"):
        return None

    min_notify = getattr(settings, "ELITE_SCORE_NOTIFY", 65)
    if elite_score is not None and elite_score < min_notify:
        return None

    now = datetime.now(VN_TZ)
    start_dt = parse_vietnam_time(voucher.start_time)
    if not start_dt:
        return None

    diff_seconds = (start_dt - now).total_seconds()
    if 0 < diff_seconds <= 2 * 60:
        return "REMINDER_2M"
    elif 2 * 60 < diff_seconds <= 15 * 60:
        return "REMINDER_15M"
    elif 15 * 60 < diff_seconds <= 24 * 3600:
        return "REMINDER_24H"

    return None

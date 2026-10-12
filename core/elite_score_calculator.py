import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Tuple, Optional
from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus
from core.elite_voucher_filter import extract_voucher_fields

VN_TZ = timezone(timedelta(hours=7))

def parse_vietnam_dt(time_str: str) -> Optional[datetime]:
    if not time_str:
        return None
    time_str = str(time_str).strip()
    try:
        dt = datetime.fromisoformat(time_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=VN_TZ)
        return dt.astimezone(VN_TZ)
    except Exception:
        pass
    m_full = re.search(r'(\d{1,2}):(\d{2})(?:\s*ngày)?\s+(\d{1,2})/(\d{1,2})(?:/(\d{4}))?', time_str)
    if m_full:
        hour, minute, day, month = map(int, m_full.groups()[:4])
        year = int(m_full.group(5)) if m_full.group(5) else datetime.now(VN_TZ).year
        try:
            return datetime(year, month, day, hour, minute, tzinfo=VN_TZ)
        except ValueError:
            pass
    return None

def calculate_elite_score(
    voucher: Dict[str, Any] or Voucher,
    is_tracked_shop: bool = False,
    is_personal_eligible: bool = False
) -> Tuple[int, str, Dict[str, int]]:
    """
    Tính thang điểm Elite Voucher Score (0–100) theo 6 tiêu chí:
    1. Giá trị giảm thực tế: tối đa 30đ
    2. Tỷ lệ giảm: tối đa 20đ
    3. Điều kiện đơn tối thiểu: tối đa 20đ
    4. Phạm vi áp dụng: tối đa 10đ
    5. Độ tin cậy & khả năng sử dụng: tối đa 15đ
    6. Tính khẩn cấp: tối đa 5đ
    
    Trả về: (total_score, label, breakdown_dict)
    """
    dtype, dval, max_d, min_o = extract_voucher_fields(voucher)

    # ---------------- 5.1. GIÁ TRỊ GIẢM THỰC TẾ (TỐI ĐA 30 ĐIỂM) ----------------
    if dtype in ("FIXED", "FIXED_AMOUNT"):
        real_saving = dval
    else:
        if min_o > 0:
            real_saving = min(min_o * (dval / 100.0), max_d if max_d is not None else 0)
        else:
            real_saving = max_d if max_d is not None else dval

    if real_saving >= 500000.0:
        score_saving = 35
    elif real_saving >= 200000.0:
        score_saving = 30
    elif real_saving >= 100000.0:
        score_saving = 28
    elif real_saving >= 50000.0:
        score_saving = 18
    elif real_saving >= 30000.0:
        score_saving = 10
    else:
        score_saving = 0

    # ---------------- 5.2. TỶ LỆ GIẢM (TỐI ĐA 20 ĐIỂM) ----------------
    if dtype in ("PERCENT", "PERCENTAGE"):
        discount_rate = dval
    else:
        if min_o == 0:
            discount_rate = 100.0
        else:
            discount_rate = (dval / min_o) * 100.0

    if discount_rate >= 50.0:
        score_rate = 20
    elif discount_rate >= 40.0:
        score_rate = 15
    elif discount_rate >= 30.0:
        score_rate = 10
    elif real_saving >= 100000.0 and discount_rate >= 15.0:
        # Mã to giảm >= 100k tiền mặt, tỷ lệ từ 15% - 29% vẫn là deal rất giá trị
        score_rate = 10
    else:
        score_rate = 0

    # ---------------- 5.3. ĐIỀU KIỆN ĐƠN TỐI THIỂU (TỐI ĐA 20 ĐIỂM) ----------------
    if min_o == 0:
        score_min_order = 20
    else:
        base_divisor = dval if dtype in ("FIXED", "FIXED_AMOUNT") else (max_d or 50000.0)
        ratio = min_o / base_divisor if base_divisor > 0 else 999.0
        if ratio <= 2.0:
            score_min_order = 16
        elif ratio <= 3.0:
            score_min_order = 14 if real_saving >= 100000.0 else 12
        elif ratio <= 4.0:
            score_min_order = 12 if real_saving >= 100000.0 else 5
        elif ratio <= 5.0 and real_saving >= 100000.0:
            score_min_order = 10
        elif ratio <= 8.0 and real_saving >= 100000.0:
            score_min_order = 6
        else:
            score_min_order = 0

    # ---------------- 5.4. PHẠM VI ÁP DỤNG (TỐI ĐA 10 ĐIỂM) ----------------
    if isinstance(voucher, Voucher):
        scope = voucher.scope_type.value if isinstance(voucher.scope_type, ScopeType) else str(voucher.scope_type)
        shop_id = voucher.shop_id
    else:
        scope = str(voucher.get("scope_type") or voucher.get("voucher_type") or "PLATFORM").upper()
        shop_id = voucher.get("shop_id")

    if scope == "PLATFORM" or "PLATFORM" in scope:
        score_scope = 10
    elif scope == "CATEGORY" or "CAT" in scope or "LIVE" in scope:
        score_scope = 7
    elif scope == "SHOP" or shop_id:
        if is_tracked_shop:
            score_scope = 8
        else:
            score_scope = 3
    else:
        score_scope = 0

    # ---------------- 5.5. ĐỘ TIN CẬY & KHẢ NĂNG SỬ DỤNG (TỐI ĐA 15 ĐIỂM) ----------------
    score_trust = 0
    # Nguồn chính thức/công khai có xác minh: 5đ
    if isinstance(voucher, Voucher):
        src_type = str(voucher.source_type or "").upper()
        status_val = voucher.status.value if isinstance(voucher.status, VoucherStatus) else str(voucher.status)
        start_t = voucher.start_time
        end_t = voucher.end_time
    else:
        src_type = str(voucher.get("source_type", "")).upper()
        status_val = str(voucher.get("status", "ACTIVE")).upper()
        start_t = voucher.get("start_time", "")
        end_t = voucher.get("end_time", "")

    if any(k in src_type for k in ("CAMPAIGN", "OFFICIAL", "PUBLIC", "SHOP")):
        score_trust += 5
    else:
        score_trust += 3

    # Còn lượt hoặc trạng thái chưa rõ nhưng chưa hết hạn: 3đ
    if status_val not in ("EXPIRED", "EXHAUSTED", "CANCELLED"):
        score_trust += 3

    # Có thông tin thời gian bắt đầu/kết thúc rõ: 3đ
    if start_t and end_t:
        score_trust += 3

    # Đã xác nhận đủ điều kiện cho tài khoản qua tích hợp chính thức: 4đ
    if is_personal_eligible:
        score_trust += 4

    score_trust = min(15, score_trust)

    # ---------------- 5.6. TÍNH KHẨN CẤP (TỐI ĐA 5 ĐIỂM) ----------------
    score_urgency = 1
    now = datetime.now(VN_TZ)
    start_dt = parse_vietnam_dt(start_t)
    end_dt = parse_vietnam_dt(end_t)

    if start_dt and start_dt > now:
        diff_start = (start_dt - now).total_seconds()
        if 0 < diff_start <= 24 * 3600:
            score_urgency = 3
    elif end_dt and now < end_dt:
        diff_end = (end_dt - now).total_seconds()
        if 0 < diff_end <= 2 * 3600:
            score_urgency = 5
        elif 0 < diff_end <= 24 * 3600:
            score_urgency = 3

    # ---------------- TỔNG ĐIỂM & GẮN NHÃN ----------------
    total_score = score_saving + score_rate + score_min_order + score_scope + score_trust + score_urgency
    total_score = max(0, min(100, total_score))

    if total_score >= 80:
        label = "🔥 SIÊU XỊN"
    elif total_score >= 70:
        label = "💎 ĐÁNG LẤY"
    else:
        label = "Không đủ chuẩn"

    breakdown = {
        "saving": score_saving,
        "rate": score_rate,
        "min_order": score_min_order,
        "scope": score_scope,
        "trust": score_trust,
        "urgency": score_urgency,
        "total": total_score
    }

    return total_score, label, breakdown

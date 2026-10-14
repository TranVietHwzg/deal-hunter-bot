import re
from typing import Dict, Any, Tuple, Optional
from models.voucher import Voucher, DiscountType, VerificationStatus

from config.settings import settings

# Danh sách từ khóa cấm tuyệt đối (Freeship / Vận chuyển)
FREESHIP_KEYWORDS = [
    "freeship", "free ship", "free shipping", "miễn phí vận chuyển", 
    "mien phi van chuyen", "hỗ trợ phí vận chuyển", "ho tro van chuyen", 
    "trợ giá ship", "tro gia ship", "mã vận chuyển", "ma van chuyen",
    "shipping fee", "hỗ trợ ship"
]

def is_freeship(data: Dict[str, Any] or Voucher) -> Tuple[bool, str]:
    """
    Kiểm tra triệt để xem voucher có phải là mã freeship/vận chuyển hay không.
    Chỉ quét title và voucher_type, KHÔNG quét description hay category_names để tránh loại nhầm sản phẩm.
    """
    if isinstance(data, Voucher):
        if data.is_freeship != 0:
            return True, "Trường is_freeship != 0"
        title = data.title or ""
        vtype = str(data.scope_type.value if hasattr(data.scope_type, 'value') else data.scope_type)
    else:
        if data.get("is_freeship") and int(data.get("is_freeship")) != 0:
            return True, "Trường is_freeship != 0"
        title = str(data.get("title", ""))
        vtype = str(data.get("voucher_type", "") or data.get("scope_type", ""))

    text_to_scan = f"{title} {vtype}".lower()

    for kw in FREESHIP_KEYWORDS:
        if kw in text_to_scan:
            return True, f"Phát hiện từ khóa cấm freeship: '{kw}'"

    return False, ""


def is_new_user_voucher(data: Dict[str, Any] or Voucher) -> bool:
    """Kiểm tra xem voucher có dành riêng cho người dùng mới không."""
    if isinstance(data, Voucher):
        text = f"{data.title} {data.description or ''}".lower()
    else:
        text = f"{data.get('title', '')} {data.get('description', '')}".lower()
    keywords = ["khách hàng mới", "người dùng mới", "đơn đầu tiên", "new user", "first order", "chỉ cho bạn mới"]
    return any(kw in text for kw in keywords)


def extract_voucher_fields(data: Dict[str, Any] or Voucher) -> Tuple[str, float, Optional[float], float]:
    """Trích xuất (discount_type, discount_value, max_discount, min_order_value)"""
    if isinstance(data, Voucher):
        dtype = data.discount_type.value if isinstance(data.discount_type, DiscountType) else str(data.discount_type).upper()
        dval = float(data.discount_value or 0)
        max_d = float(data.max_discount) if data.max_discount is not None else None
        min_o = float(data.min_order_value or 0)
    else:
        dtype = str(data.get("discount_type", "FIXED")).upper()
        dval = float(data.get("discount_value", 0) or 0)
        raw_max = data.get("max_discount") or data.get("max_discount_amount")
        max_d = float(raw_max) if raw_max is not None else None
        min_o = float(data.get("min_order_value", 0) or data.get("min_spend", 0) or 0)
    return dtype, dval, max_d, min_o


def is_elite_voucher(
    data: Dict[str, Any] or Voucher,
    allow_new_user: bool = False,
    require_evidence: bool = False
) -> Tuple[bool, str]:
    """
    Cổng lọc cứng kiểm duyệt Elite Shopee Voucher Radar:
    - Loại bỏ 100% Freeship
    - Loại bỏ mã người dùng mới nếu allow_new_user = False
    - Kiểm tra bằng chứng bắt buộc (source_url, start_time, end_time, verification_status)
    - Nhánh 1: Mã giảm tiền cố định:
        A. discount_value >= 30.000đ và min_order_value == 0đ
        B. discount_value >= 50.000đ và min_order_value / discount_value <= 3.0
    - Nhánh 2: Mã giảm phần trăm:
        - discount_percent >= 30%
        - max_discount >= 50.000đ
        - min_order_value không quá cao so với max_discount (min_order_value <= max_discount * 4.0)
        - estimated_saving_at_minimum_order >= 30.000đ
    """
    # 1. Chặn Freeship
    is_ship, reason = is_freeship(data)
    if is_ship:
        return False, f"Loại: {reason}"

    # 2. Chặn New User
    if not allow_new_user and is_new_user_voucher(data):
        return False, "Loại: Voucher chỉ dành cho người dùng mới"

    # 3. Kiểm tra bằng chứng và trạng thái xác minh (Verification Status)
    if isinstance(data, Voucher):
        v_status = data.verification_status
        src_url = data.source_url
        start_t = data.start_time
        end_t = data.end_time
        v_code = data.voucher_code
        has_status_field = True
    else:
        v_status = data.get("verification_status")
        src_url = data.get("source_url") or data.get("claim_url")
        start_t = data.get("start_time")
        end_t = data.get("end_time")
        v_code = data.get("voucher_code")
        has_status_field = "verification_status" in data or "source_url" in data or "start_time" in data or require_evidence

    # Nếu voucher có trường trạng thái xác minh hoặc yêu cầu bằng chứng:
    if has_status_field or require_evidence:
        # A. Cấm tuyệt đối TEST_DATA / MOCK / SEED
        if v_status in (VerificationStatus.TEST_DATA, "TEST_DATA"):
            return False, "Loại: Mã kiểm thử/mock/seed (TEST_DATA)"

        # B. Cấm INVALID / EXPIRED
        if v_status in (VerificationStatus.INVALID, "INVALID") or str(data.get("status") if isinstance(data, dict) else data.status.value).upper() == "EXPIRED":
            return False, "Loại: Voucher bị đánh dấu INVALID hoặc EXPIRED"

        # C. Cấm UNVERIFIED
        if v_status in (VerificationStatus.UNVERIFIED, "UNVERIFIED"):
            return False, "Loại: Chưa có bằng chứng xác minh (UNVERIFIED)"

        # D. Cấm PERSONAL_ELIGIBILITY_UNKNOWN vào Elite tự động
        if v_status in (VerificationStatus.PERSONAL_ELIGIBILITY_UNKNOWN, "PERSONAL_ELIGIBILITY_UNKNOWN"):
            return False, "Loại: Chưa xác minh điều kiện tài khoản cá nhân (PERSONAL_ELIGIBILITY_UNKNOWN)"

        # E. Cấm UPCOMING_UNKNOWN_CODE (chưa có code thật và không phải nút lưu trực tiếp)
        claim_t = data.get("claim_type") if isinstance(data, dict) else getattr(data, "claim_type", "CODE")
        if v_status in (VerificationStatus.UPCOMING_UNKNOWN_CODE, "UPCOMING_UNKNOWN_CODE"):
            return False, "Loại: Chưa có mã voucher code (UPCOMING_UNKNOWN_CODE)"
        if not v_code and claim_t != "SAVE_BUTTON":
            return False, "Loại: Chưa có mã voucher code"

        # F. Kiểm tra source_url
        if not src_url or not str(src_url).strip() or str(src_url).strip() in ("None", ""):
            return False, "Loại: Thiếu source_url bằng chứng hợp lệ"

        # G. Kiểm tra start_time và end_time
        if not start_t or not str(start_t).strip() or not end_t or not str(end_t).strip():
            return False, "Loại: Thiếu start_time hoặc end_time hiệu lực rõ ràng"

        # H. Chỉ cho phép VERIFIED_ACTIVE, VERIFIED_UPCOMING hoặc COMMUNITY_LEAK (Mã leak cộng đồng có code)
        raw_vs = v_status.value if isinstance(v_status, VerificationStatus) else str(v_status)
        if raw_vs not in ("VERIFIED_ACTIVE", "VERIFIED_UPCOMING", "COMMUNITY_LEAK"):
            return False, f"Loại: Trạng thái xác minh '{raw_vs}' không đủ chuẩn Elite"

    dtype, dval, max_d, min_o = extract_voucher_fields(data)

    # 3. Phân nhánh kiểm duyệt
    if dtype in ("FIXED", "FIXED_AMOUNT"):
        # Phải giảm ít nhất 30.000đ
        if dval < 30000.0:
            return False, f"Loại: Mức giảm cố định {int(dval):,}đ < 30.000đ"

        # Điều kiện A: Giảm >= 30k đơn 0đ
        if dval >= 30000.0 and min_o == 0:
            return True, "Đạt Elite: Giảm >= 30k đơn 0đ"

        # Điều kiện C: Mã TO (giảm >= 100k) cho phép tỷ lệ đơn tối thiểu đến 5.0 (Ví dụ: 100k/500k, 500k/2.5tr, 1M/5tr)
        if dval >= 100000.0:
            ratio = min_o / dval
            if ratio <= 5.0:
                return True, f"Đạt Elite Mã To: Giảm {int(dval):,}đ đơn {int(min_o):,}đ (tỷ lệ {ratio:.1f} <= 5)"
            else:
                return False, f"Loại: Điều kiện đơn quá cao cho mã to (tỷ lệ {ratio:.1f} > 5)"

        # Điều kiện B: Giảm >= 50k và min_order / discount <= 3
        if dval >= 50000.0:
            ratio = min_o / dval
            if ratio <= 3.0:
                return True, f"Đạt Elite: Giảm {int(dval):,}đ đơn {int(min_o):,}đ (tỷ lệ {ratio:.1f} <= 3)"
            else:
                return False, f"Loại: Điều kiện đơn quá cao (tỷ lệ {ratio:.1f} > 3)"

        return False, f"Loại: Giảm {int(dval):,}đ nhưng đơn tối thiểu {int(min_o):,}đ > 0đ"

    elif dtype in ("PERCENT", "PERCENTAGE"):
        min_pct = getattr(settings, "ELITE_MIN_PERCENT", 30.0)
        min_cap = getattr(settings, "ELITE_MIN_CAP", 30000.0)

        # Phải giảm ít nhất 30%
        if dval < min_pct:
            return False, f"Loại: Giảm {dval:.0f}% < {min_pct:.0f}%"

        # Phải có trần giảm rõ ràng và >= 30.000đ
        if max_d is None:
            return False, "Loại: Giảm % nhưng không công bố mức giảm tối đa"
        if max_d < min_cap:
            return False, f"Loại: Mức giảm tối đa {int(max_d):,}đ < {int(min_cap):,}đ"

        # Kiểm tra điều kiện đơn tối thiểu không quá cao so với max_discount
        # Cho phép trần >= 100k có đơn tối thiểu đến 8 lần trần giảm (Ví dụ: 30% tối đa 100k đơn 800k)
        max_ratio_allowed = 8.0 if max_d >= 100000.0 else 4.0
        if min_o > max_d * max_ratio_allowed:
            return False, f"Loại: Điều kiện đơn {int(min_o):,}đ quá cao so với trần giảm {int(max_d):,}đ (vượt {max_ratio_allowed:.0f}x)"

        # Tính tiết kiệm ước tính tại đơn tối thiểu
        # estimated_saving_at_minimum_order = min(min_order_value * (discount_percent / 100), max_discount)
        if min_o > 0:
            est_saving = min(min_o * (dval / 100.0), max_d)
        else:
            # Đơn 0đ thì tiết kiệm được tính theo trần giảm
            est_saving = max_d

        if est_saving < 30000.0:
            return False, f"Loại: Tiết kiệm ước tính tại đơn tối thiểu {int(est_saving):,}đ < 30.000đ"

        return True, f"Đạt Elite: Giảm {dval:.0f}% tối đa {int(max_d):,}đ (tiết kiệm min_order {int(est_saving):,}đ)"

    return False, f"Loại: Kiểu giảm giá không hợp lệ: {dtype}"


def is_zero_dong_affiliate_voucher(data: Dict[str, Any] or Voucher) -> bool:
    """
    Bộ lọc cứng 'Chuẩn Đơn 0Đ' chuyên biệt cho mã độc quyền tiếp thị liên kết:
    1. Tuyệt đối loại bỏ Freeship.
    2. ĐIỀU KIỆN TIÊN QUYẾT: Đơn tối thiểu bắt buộc phải bằng 0đ (min_order_value <= 0).
    3. Mã giảm tiền cố định: Giảm từ 30.000đ đến 1.000.000đ+ đơn 0đ.
    4. Mã giảm phần trăm: Giảm từ 30% trở lên đơn 0đ, trần giảm >= 30.000đ.
    """
    ship, _ = is_freeship(data)
    if ship:
        return False

    dtype, dval, max_d, min_o = extract_voucher_fields(data)

    # 1. BẮT BUỘC ĐƠN TỐI THIỂU BẰNG 0Đ
    if min_o > 0:
        return False

    # 2. Mã giảm tiền cố định >= 30k
    if dtype in ("FIXED", "FIXED_AMOUNT"):
        return dval >= 30000.0

    # 3. Mã giảm phần trăm >= 30%, trần >= 30k
    if dtype in ("PERCENT", "PERCENTAGE"):
        cap = max_d if max_d is not None else 0
        return dval >= 30.0 and cap >= 30000.0

    return False


def classify_voucher_quality(data: Dict[str, Any] or Voucher) -> Dict[str, Any]:
    """
    Phân loại nhãn chất lượng độc lập theo thiết kế kiến trúc chuẩn:
    - Loại trừ: Freeship, hết hạn, hủy, không hợp lệ
    - ZERO_DONG_AFFILIATE: Đạt chuẩn mã độc quyền tiếp thị đơn 0đ (>=30k đơn 0đ hoặc >=30% trần >=30k đơn 0đ)
    - HIGH_RATE: Giảm >= 30% (kể cả trần nhỏ, nhằm bắt trọn deal tỷ lệ cao)
    - ELITE_VALUE: Giảm >= 30.000đ đơn 0đ HOẶC giảm >= 30% với mức tiết kiệm dự kiến >= 30.000đ
      (Bao gồm mã TO: giảm >= 100k với ratio <= 5.0, trần >= 100k với ratio <= 8.0)
    """
    ship, reason = is_freeship(data)
    if ship:
        return {"is_qualified": False, "tags": [], "reason": f"Loại freeship: {reason}"}

    dtype, dval, max_d, min_o = extract_voucher_fields(data)
    tags = []
    min_pct = getattr(settings, "ELITE_MIN_PERCENT", 30.0)
    min_cap = getattr(settings, "ELITE_MIN_CAP", 30000.0)
    min_fixed = getattr(settings, "ELITE_MIN_FIXED_0D", 30000.0)

    # Ưu tiên kiểm tra nhãn đơn 0đ
    if is_zero_dong_affiliate_voucher(data):
        tags.append("ZERO_DONG_AFFILIATE")

    if dtype in ("PERCENT", "PERCENTAGE"):
        if dval >= min_pct:
            tags.append("HIGH_RATE")
            effective_saving = max_d if (max_d is not None) else (min_o * (dval / 100.0) if min_o > 0 else 0)
            max_ratio = 8.0 if (max_d is not None and max_d >= 100000.0) else 4.0
            if (max_d is not None and max_d >= min_cap and min_o <= max_d * max_ratio) or effective_saving >= min_cap:
                tags.append("ELITE_VALUE")

    elif dtype in ("FIXED", "FIXED_AMOUNT"):
        if dval >= min_fixed and min_o == 0:
            tags.append("ELITE_VALUE")
        elif dval >= 100000.0 and (min_o / dval <= 5.0):
            tags.append("ELITE_VALUE")
        elif dval >= 50000.0 and (min_o / dval <= 3.0):
            tags.append("ELITE_VALUE")

    is_qualified = len(tags) > 0
    return {
        "is_qualified": is_qualified,
        "tags": tags,
        "reason": f"Đạt nhãn {', '.join(tags)}" if tags else "Không đạt tiêu chí 30k/0đ hoặc >=30%"
    }


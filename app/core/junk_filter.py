import re
from typing import Dict, Any, Tuple
from datetime import datetime, timezone

# Regex loại bỏ 100% mọi hình thức voucher hỗ trợ phí vận chuyển
FREESHIP_EXCLUSION_PATTERN = re.compile(
    r"(?i)\b("
    r"freeship|free\s*shipping|miễn\s*phí\s*vận\s*chuyển|phí\s*vận\s*chuyển|"
    r"vận\s*chuyển|phí\s*ship|tiền\s*ship|hỗ\s*trợ\s*ship|trợ\s*giá\s*ship|tro\s*gia\s*ship|"
    r"shipping\s*fee|shipping\s*subsidy|ship\s*0đ|ship\s*0d|giao\s*hàng\s*0đ|giao\s*hàng\s*miễn\s*phí"
    r")\b"
)

# Từ khóa nghi vấn rác hoặc lừa đảo
SPAM_JUNK_PATTERN = re.compile(
    r"(?i)\b(lừa\s*đảo|click\s*vào\s*link\s*lạ|trúng\s*thưởng\s*100%|vay\s*tiền|tặng\s*tiền\s*mặt)\b"
)

def is_freeship(voucher_data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Kiểm tra xem voucher có dính dáng tới Freeship hay không.
    Trả về: (True, lý do) nếu là voucher freeship (PHẢI LOẠI BỎ).
    """
    # 1. Kiểm tra trường voucher_type hoặc category
    v_type = str(voucher_data.get("voucher_type", "")).upper()
    if any(k in v_type for k in ["SHIP", "FREESHIP", "LOGISTIC", "DELIVERY"]):
        return True, f"Loại voucher '{v_type}' là mã vận chuyển"

    # 2. Kiểm tra discount_target của sàn (Shopee/Lazada API)
    target = str(voucher_data.get("discount_target", "")).lower()
    if target in ["shipping_fee", "shipping", "shipping_subsidy", "delivery"]:
        return True, f"Mục tiêu giảm giá '{target}' là cước vận chuyển"

    # 3. Quét toàn bộ nội dung text (tiêu đề, nhãn, mã, mô tả)
    text_corpus = " ".join([
        str(voucher_data.get("title", "")),
        str(voucher_data.get("label", "")),
        str(voucher_data.get("description", "")),
        str(voucher_data.get("voucher_code", "")),
        str(voucher_data.get("discount_desc", ""))
    ])

    if FREESHIP_EXCLUSION_PATTERN.search(text_corpus):
        return True, "Nội dung voucher chứa từ khóa Freeship / Vận chuyển"

    # 4. Kiểm tra flag is_freeship nếu có
    if voucher_data.get("is_freeship") is True:
        return True, "Trường is_freeship được đánh dấu True"

    return False, ""

def validate_voucher(voucher_data: Dict[str, Any], allow_new_user: bool = False) -> Tuple[bool, str]:
    """
    Bộ lọc chống voucher rác toàn diện.
    Trả về: (is_valid, reason)
    """
    # BƯỚC 1: BÀI TRỪ FREESHIP TUYỆT ĐỐI
    is_ship, ship_reason = is_freeship(voucher_data)
    if is_ship:
        return False, f"TRẢM FREESHIP: {ship_reason}"

    # BƯỚC 2: Kiểm tra từ khóa rác / spam
    text_corpus = f"{voucher_data.get('title', '')} {voucher_data.get('description', '')}"
    if SPAM_JUNK_PATTERN.search(text_corpus):
        return False, "Voucher chứa từ khóa rác / lừa đảo"

    # BƯỚC 3: Kiểm tra voucher tân thủ / người dùng mới
    is_new_user = voucher_data.get("is_new_user_only", False)
    if is_new_user and not allow_new_user:
        return False, "Voucher chỉ dành cho khách hàng mới (Đang cấu hình tắt)"

    # BƯỚC 4: Kiểm tra trạng thái hết hạn / hết lượt
    status = str(voucher_data.get("status", "ACTIVE")).upper()
    if status in ["EXHAUSTED", "HET_LUOT"]:
        return False, "Voucher đã hết lượt sử dụng"
    if status in ["EXPIRED", "HET_HAN"]:
        return False, "Voucher đã hết thời hạn hiệu lực"

    # Kiểm tra thời gian hết hạn nếu có (Fail-Closed: nếu có end_time mà không parse được hoặc đã qua -> False)
    end_time_raw = voucher_data.get("end_time")
    if end_time_raw:
        from core.voucher_lifecycle import parse_vietnam_time, VN_TZ
        dt = None
        if isinstance(end_time_raw, (int, float)):
            try:
                dt = datetime.fromtimestamp(end_time_raw, tz=VN_TZ)
            except Exception:
                return False, "end_time không parse được"
        elif isinstance(end_time_raw, str):
            dt = parse_vietnam_time(end_time_raw)
            if not dt:
                try:
                    clean_iso = end_time_raw.replace("Z", "+00:00")
                    dt_iso = datetime.fromisoformat(clean_iso)
                    dt = dt_iso.astimezone(VN_TZ) if dt_iso.tzinfo else dt_iso.replace(tzinfo=VN_TZ)
                except Exception:
                    pass

        if dt is None:
            return False, "end_time không parse được"

        now = datetime.now(VN_TZ)
        if dt < now:
            return False, "Voucher đã quá hạn sử dụng"

    # BƯỚC 5: Kiểm tra tính đầy đủ của điều kiện
    discount_val = voucher_data.get("discount_value") or voucher_data.get("discount_val") or 0
    if float(discount_val) <= 0:
        return False, "Voucher không có giá trị giảm hợp lệ (> 0)"

    min_spend = voucher_data.get("min_spend", 0)
    if min_spend is None or min_spend < 0:
        return False, "Điều kiện đơn tối thiểu không hợp lệ"

    return True, "Hợp lệ"

import re
from typing import Dict, Any, Tuple, Optional
from models.voucher import Voucher, DiscountType

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
    Chỉ quét title và voucher_type, KHÔNG quét description hay category_names để tránh loại nhầm hàng giảm giá.
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
            return True, f"Phát hiện từ khóa cấm: '{kw}'"

    return False, ""

def is_worthy_voucher(
    voucher: Voucher or Dict[str, Any],
    min_fixed_discount: Optional[float] = None,
    min_percent_rate: Optional[float] = None,
    min_percent_cap: Optional[float] = None
) -> bool:
    """
    Tiêu chuẩn voucher 'xịn' đáng phát cảnh báo (Single Source of Truth từ config/settings.py):
    - Mặc định: Giảm tiền từ 30.000đ; hoặc giảm từ 30% với trần từ 30.000đ.
    """
    if min_fixed_discount is None:
        min_fixed_discount = getattr(settings, "ELITE_MIN_FIXED_0D", 30000.0)
    if min_percent_rate is None:
        min_percent_rate = getattr(settings, "ELITE_MIN_PERCENT", 30.0)
    if min_percent_cap is None:
        min_percent_cap = getattr(settings, "ELITE_MIN_CAP", 30000.0)

    if isinstance(voucher, Voucher):
        dtype = voucher.discount_type.value if isinstance(voucher.discount_type, DiscountType) else str(voucher.discount_type)
        dval = float(voucher.discount_value)
        max_d = float(voucher.max_discount) if voucher.max_discount is not None else dval
    else:
        dtype = str(voucher.get("discount_type", "FIXED")).upper()
        dval = float(voucher.get("discount_value", 0))
        max_d = float(voucher.get("max_discount", 0) or voucher.get("max_discount_amount", 0) or dval)

    if dtype in ("FIXED", "FIXED_AMOUNT"):
        return dval >= min_fixed_discount
    elif dtype in ("PERCENT", "PERCENTAGE"):
        is_high_rate = (dval >= min_percent_rate) and (max_d >= min_percent_cap)
        is_big_cap = (max_d >= 100000.0) and (dval >= 10.0)
        return is_high_rate or is_big_cap

    return False


def _get_numbers(voucher: Voucher or Dict[str, Any]):
    if isinstance(voucher, Voucher):
        dtype = voucher.discount_type.value if isinstance(voucher.discount_type, DiscountType) else str(voucher.discount_type)
        dval = float(voucher.discount_value)
        max_d = float(voucher.max_discount) if voucher.max_discount is not None else dval
        min_o = float(voucher.min_order_value or 0)
    else:
        dtype = str(voucher.get("discount_type", "FIXED")).upper()
        dval = float(voucher.get("discount_value", 0))
        max_d = float(voucher.get("max_discount", 0) or voucher.get("max_discount_amount", 0) or dval)
        min_o = float(voucher.get("min_order_value", 0) or voucher.get("min_spend", 0) or 0)
    return dtype.upper(), dval, max_d, min_o


def is_super_voucher(voucher: Voucher or Dict[str, Any]) -> Tuple[bool, str]:
    """Mã siêu ngon: 100k/50k/30%+ mà đơn 0đ hoặc rẻ.
    Dùng để ưu tiên nhắc giờ, không thay thế is_worthy_voucher.
    """
    dtype, dval, max_d, min_o = _get_numbers(voucher)
    if dtype in ("FIXED", "FIXED_AMOUNT"):
        if dval >= 100000 and min_o <= 100000:
            return True, "SUPER_100K_0D"
        if dval >= 50000 and min_o <= 50000:
            return True, "SUPER_50K_0D"
        if dval >= 30000 and min_o == 0:
            return True, "SUPER_30K_0D"
    elif dtype in ("PERCENT", "PERCENTAGE"):
        if dval >= 30 and max_d >= 100000:
            return True, "SUPER_30PCT"
        if dval >= 20 and max_d >= 150000 and min_o <= 400000:
            return True, "SUPER_20PCT"
    return False, ""


def score_voucher(voucher: Voucher or Dict[str, Any]) -> int:
    """Chấm 0-100 để xếp hạng /top: đơn càng rẻ + giảm càng to càng cao."""
    dtype, dval, max_d, min_o = _get_numbers(voucher)
    if dtype in ("FIXED", "FIXED_AMOUNT"):
        real = dval
    else:
        real = max_d
    if real <= 0:
        return 0
    # Điểm gốc theo giá trị thật
    base = min(70, real / 200000 * 70)
    # Thưởng đơn rẻ
    if min_o == 0:
        base += 30
    elif min_o <= 50000:
        base += 20
    elif min_o <= 200000:
        base += 10
    elif min_o > real * 8:
        base -= 20
    # Thưởng % cao
    if dtype in ("PERCENT", "PERCENTAGE") and dval >= 30:
        base += 10
    return max(0, min(100, int(base)))

def validate_voucher_for_radar(data: Dict[str, Any] or Voucher) -> Tuple[bool, str]:
    """Kiểm tra tính hợp lệ toàn diện của voucher trước khi lưu vào Radar"""
    is_ship, reason = is_freeship(data)
    if is_ship:
        return False, f"Bị loại: {reason}"
    return True, "Hợp lệ"

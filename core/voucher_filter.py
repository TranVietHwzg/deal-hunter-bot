import re
from typing import Dict, Any, Tuple, Optional
from models.voucher import Voucher, DiscountType

# Danh sách từ khóa cấm tuyệt đối (Freeship / Vận chuyển)
FREESHIP_KEYWORDS = [
    "freeship", "free ship", "free shipping", "miễn phí vận chuyển", 
    "mien phi van chuyen", "hỗ trợ phí vận chuyển", "ho tro van chuyen", 
    "trợ giá ship", "tro gia ship", "mã vận chuyển", "ma van chuyen",
    "giảm cước", "giao hàng", "phí giao hàng", "shipping fee", "hỗ trợ ship"
]

def is_freeship(data: Dict[str, Any] or Voucher) -> Tuple[bool, str]:
    """
    Kiểm tra triệt để 100% xem voucher có phải là mã freeship/vận chuyển hay không.
    Trả về (True, lý_do) nếu là freeship, (False, "") nếu là voucher giảm giá hàng hợp lệ.
    """
    if isinstance(data, Voucher):
        if data.is_freeship != 0:
            return True, "Trường is_freeship != 0"
        text_corpus = f"{data.title} {data.description or ''} {' '.join(data.category_names)} {data.source_type}".lower()
    else:
        if data.get("is_freeship") and int(data.get("is_freeship")) != 0:
            return True, "Trường is_freeship != 0"
        title = str(data.get("title", ""))
        desc = str(data.get("description", ""))
        vtype = str(data.get("voucher_type", "") or data.get("scope_type", ""))
        cat = str(data.get("category", "") or data.get("category_names", ""))
        text_corpus = f"{title} {desc} {vtype} {cat}".lower()

    for kw in FREESHIP_KEYWORDS:
        if kw in text_corpus:
            return True, f"Phát hiện từ khóa cấm: '{kw}'"

    return False, ""

def is_worthy_voucher(
    voucher: Voucher or Dict[str, Any],
    min_fixed_discount: float = 50000.0,
    min_percent_rate: float = 15.0,
    min_percent_cap: float = 100000.0
) -> bool:
    """
    Tiêu chuẩn voucher 'xịn' đáng phát cảnh báo:
    - Giảm tiền cố định từ 50.000đ; hoặc
    - Giảm từ 15% trở lên với mức giảm tối đa từ 100.000đ; hoặc
    - Thỏa mãn cấu hình riêng của người dùng.
    """
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
        return (dval >= min_percent_rate) and (max_d >= min_percent_cap)

    return False

def validate_voucher_for_radar(data: Dict[str, Any] or Voucher) -> Tuple[bool, str]:
    """Kiểm tra tính hợp lệ toàn diện của voucher trước khi lưu vào Radar"""
    is_ship, reason = is_freeship(data)
    if is_ship:
        return False, f"Bị loại: {reason}"
    return True, "Hợp lệ"

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
    allow_new_user: bool = False
) -> Tuple[bool, str]:
    """
    Cổng lọc cứng kiểm duyệt Elite Shopee Voucher Radar:
    - Loại bỏ 100% Freeship
    - Loại bỏ mã người dùng mới nếu allow_new_user = False
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

    dtype, dval, max_d, min_o = extract_voucher_fields(data)

    # 3. Phân nhánh kiểm duyệt
    if dtype in ("FIXED", "FIXED_AMOUNT"):
        # Phải giảm ít nhất 30.000đ
        if dval < 30000.0:
            return False, f"Loại: Mức giảm cố định {int(dval):,}đ < 30.000đ"

        # Điều kiện A: Giảm >= 30k đơn 0đ
        if dval >= 30000.0 and min_o == 0:
            return True, "Đạt Elite: Giảm >= 30k đơn 0đ"

        # Điều kiện B: Giảm >= 50k và min_order / discount <= 3
        if dval >= 50000.0:
            ratio = min_o / dval
            if ratio <= 3.0:
                return True, f"Đạt Elite: Giảm {int(dval):,}đ đơn {int(min_o):,}đ (tỷ lệ {ratio:.1f} <= 3)"
            else:
                return False, f"Loại: Điều kiện đơn quá cao (tỷ lệ {ratio:.1f} > 3)"

        return False, f"Loại: Giảm {int(dval):,}đ nhưng đơn tối thiểu {int(min_o):,}đ > 0đ"

    elif dtype in ("PERCENT", "PERCENTAGE"):
        # Phải giảm ít nhất 30%
        if dval < 30.0:
            return False, f"Loại: Giảm {dval:.0f}% < 30%"

        # Phải có trần giảm rõ ràng và >= 50.000đ
        if max_d is None:
            return False, "Loại: Giảm % nhưng không công bố mức giảm tối đa"
        if max_d < 50000.0:
            return False, f"Loại: Mức giảm tối đa {int(max_d):,}đ < 50.000đ"

        # Kiểm tra điều kiện đơn tối thiểu không quá cao so với max_discount
        # Ví dụ: Giảm 30% tối đa 100k, đơn từ 2 triệu -> Loại (2tr / 100k = 20 > 4)
        if min_o > max_d * 4.0:
            return False, f"Loại: Điều kiện đơn {int(min_o):,}đ quá cao so với trần giảm {int(max_d):,}đ"

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

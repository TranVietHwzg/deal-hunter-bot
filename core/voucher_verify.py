"""Verify voucher hợp pháp - chỉ tìm, không tự claim.
Không brute-force, không gọi private API, không bypass chống bot.
Chỉ chuẩn hóa + kiểm tra metadata công khai.
"""
import re
from typing import Dict, Any, Tuple
from core.voucher_filter import is_freeship, is_worthy_voucher, score_voucher, is_super_voucher

CODE_RE = re.compile(r"^[A-Z0-9]{4,30}$")

def normalize_code(raw: str | None) -> str | None:
    if not raw:
        return None
    c = str(raw).strip().upper().replace(" ", "")
    # chỉ giữ A-Z 0-9, bỏ ký tự lạ
    c = re.sub(r"[^A-Z0-9]", "", c)
    if not c:
        return None
    return c

def verify_hunt_only(item: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    """Trả về (ok, lý_do, item_đã_chuẩn_hóa). Không thực hiện claim."""
    code = normalize_code(item.get("voucher_code"))
    item = dict(item)
    item["voucher_code"] = code

    ship, reason = is_freeship(item)
    if ship:
        return False, f"loai_freeship: {reason}", item

    if code and not CODE_RE.match(code):
        return False, "ma_sai_dinh_dang", item

    try:
        dval = float(item.get("discount_value", 0) or 0)
    except Exception:
        dval = 0
    if dval <= 0:
        return False, "thieu_gia_tri_giam", item

    worthy = is_worthy_voucher(item)
    score = score_voucher(item)
    super_hit, super_tag = is_super_voucher(item)

    item["confidence_score"] = int(item.get("confidence_score", 85))
    item["_score"] = score
    item["_super"] = super_tag if super_hit else ""

    if not worthy and score < 20:
        return False, "ma_yeu_khong_dang_bao", item

    return True, "hop_le_cho_nhac_gio", item

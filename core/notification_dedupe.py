import hashlib
from typing import Dict, Any, Optional
from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus

class NotificationDedupe:
    """Hệ thống chống trùng thông báo dựa trên Fingerprint 12 trường dữ liệu bắt buộc:
    platform + voucher_code + scope_type + shop_id + discount_type +
    discount_value + discount_percent + max_discount + min_order_value +
    start_time + end_time + status
    """
    def __init__(self, scan_repo=None):
        self.scan_repo = scan_repo
        self._sent_cache = set()

    def calculate_fingerprint(self, voucher: Voucher or Dict[str, Any], event_tag: str = "") -> str:
        if isinstance(voucher, Voucher):
            platform = str(voucher.platform or "SHOPEE")
            code = str(voucher.voucher_code or "NO_CODE")
            scope = str(voucher.scope_type.value if isinstance(voucher.scope_type, ScopeType) else voucher.scope_type)
            shop_id = str(voucher.shop_id or "NO_SHOP")
            dtype = str(voucher.discount_type.value if isinstance(voucher.discount_type, DiscountType) else voucher.discount_type)
            dval = f"{float(voucher.discount_value):.2f}"
            d_pct = f"{float(voucher.discount_value):.2f}" if dtype in ("PERCENT", "PERCENTAGE") else "0.00"
            max_d = f"{float(voucher.max_discount):.2f}" if voucher.max_discount is not None else "NO_MAX"
            min_o = f"{float(voucher.min_order_value):.2f}"
            start_t = str(voucher.start_time or "")
            end_t = str(voucher.end_time or "")
            status = str(voucher.status.value if isinstance(voucher.status, VoucherStatus) else voucher.status)
        else:
            platform = str(voucher.get("platform", "SHOPEE"))
            code = str(voucher.get("voucher_code") or "NO_CODE")
            scope = str(voucher.get("scope_type") or voucher.get("voucher_type") or "PLATFORM")
            shop_id = str(voucher.get("shop_id") or "NO_SHOP")
            dtype = str(voucher.get("discount_type", "FIXED"))
            dval = f"{float(voucher.get('discount_value', 0)):.2f}"
            d_pct = f"{float(voucher.get('discount_value', 0)):.2f}" if dtype in ("PERCENT", "PERCENTAGE") else "0.00"
            max_d = f"{float(voucher.get('max_discount', 0)):.2f}" if voucher.get("max_discount") is not None else "NO_MAX"
            min_o = f"{float(voucher.get('min_order_value', 0) or voucher.get('min_spend', 0)):.2f}"
            start_t = str(voucher.get("start_time", ""))
            end_t = str(voucher.get("end_time", ""))
            status = str(voucher.get("status", "ACTIVE"))

        raw_parts = [
            platform, code, scope, shop_id, dtype,
            dval, d_pct, max_d, min_o,
            start_t, end_t, status
        ]
        if event_tag:
            raw_parts.append(event_tag)

        raw_str = "|".join(raw_parts)
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def is_duplicate(self, fingerprint: str) -> bool:
        if fingerprint in self._sent_cache:
            return True
        if self.scan_repo and hasattr(self.scan_repo, "is_fingerprint_sent"):
            return self.scan_repo.is_fingerprint_sent(fingerprint)
        return False

    def record_sent(self, fingerprint: str, voucher_id: str = "", event_type: str = "") -> None:
        self._sent_cache.add(fingerprint)
        if self.scan_repo and hasattr(self.scan_repo, "record_sent_fingerprint"):
            try:
                self.scan_repo.record_sent_fingerprint(fingerprint, voucher_id, event_type)
            except Exception:
                pass

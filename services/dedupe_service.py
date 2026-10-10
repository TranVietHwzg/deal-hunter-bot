import hashlib
from typing import Dict, Any, Optional
from models.voucher import Voucher, ScopeType, VoucherStatus
from repositories.scan_repository import ScanRepository

class DedupeService:
    def __init__(self, scan_repo: Optional[ScanRepository] = None):
        self.scan_repo = scan_repo or ScanRepository()

    @staticmethod
    def calculate_fingerprint(voucher: Voucher, event_type: str = "") -> str:
        """
        Tính toán fingerprint:
        platform + voucher_code + scope_type + shop_id + start_time + end_time + discount_value + min_order_value + status (+ event_type)
        """
        code = str(voucher.voucher_code or "NO_CODE")
        stype = voucher.scope_type.value if isinstance(voucher.scope_type, ScopeType) else str(voucher.scope_type)
        sid = str(voucher.shop_id or "NO_SHOP")
        status = voucher.status.value if isinstance(voucher.status, VoucherStatus) else str(voucher.status)
        raw_str = (
            f"{voucher.platform}_{code}_{stype}_{sid}_{voucher.start_time}_"
            f"{voucher.end_time}_{int(voucher.discount_value)}_{int(voucher.min_order_value)}_{status}_{event_type}"
        )
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def is_duplicate(self, fingerprint: str) -> bool:
        return self.scan_repo.is_notification_duplicate(fingerprint)

import hashlib
import uuid
from typing import Dict, Any, Optional
from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus
from core.voucher_lifecycle import parse_vietnam_time

class NotificationDedupe:
    """Hệ thống chống trùng thông báo.

    Đồng bộ (unify) với DedupeService:
    - Chuẩn hóa thời gian bằng parse_vietnam_time để không tạo fingerprint mới
      khi cùng một mốc thời gian được viết khác nhau.
    - KHÔNG đưa `status` vào fingerprint (tránh gửi lại khi voucher chuyển trạng thái).
    - Khi có scan_repo sẽ lưu/truy vấn bền vững qua notification_events.
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
            dval = float(voucher.discount_value or 0)
            max_d = voucher.max_discount
            min_o = float(voucher.min_order_value or 0)
            start_raw = getattr(voucher, "start_time", "")
            end_raw = getattr(voucher, "end_time", "")
        else:
            platform = str(voucher.get("platform", "SHOPEE"))
            code = str(voucher.get("voucher_code") or "NO_CODE")
            scope = str(voucher.get("scope_type") or voucher.get("voucher_type") or "PLATFORM")
            shop_id = str(voucher.get("shop_id") or "NO_SHOP")
            dtype = str(voucher.get("discount_type", "FIXED"))
            dval = float(voucher.get("discount_value", 0) or 0)
            max_d = voucher.get("max_discount", None)
            min_o = float(voucher.get("min_order_value", 0) or voucher.get("min_spend", 0) or 0)
            start_raw = voucher.get("start_time", "")
            end_raw = voucher.get("end_time", "")

        start_dt = parse_vietnam_time(str(start_raw)) if start_raw else None
        end_dt = parse_vietnam_time(str(end_raw)) if end_raw else None
        start_t = start_dt.isoformat() if start_dt else str(start_raw or "")
        end_t = end_dt.isoformat() if end_dt else str(end_raw or "")

        d_pct = f"{dval:.2f}" if dtype in ("PERCENT", "PERCENTAGE") else "0.00"
        max_d_str = f"{float(max_d):.2f}" if max_d is not None else "NO_MAX"

        raw_parts = [
            platform, code, scope, shop_id, dtype,
            f"{dval:.2f}", d_pct, max_d_str, f"{min_o:.2f}",
            start_t, end_t
        ]
        # status bị loại bỏ có chủ đích (unify với DedupeService)
        if event_tag:
            raw_parts.append(event_tag)

        raw_str = "|".join(raw_parts)
        return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()

    def is_duplicate(self, fingerprint: str) -> bool:
        if fingerprint in self._sent_cache:
            return True
        if self.scan_repo:
            if hasattr(self.scan_repo, "is_fingerprint_sent"):
                try:
                    return bool(self.scan_repo.is_fingerprint_sent(fingerprint))
                except Exception:
                    pass
            if hasattr(self.scan_repo, "is_notification_duplicate"):
                try:
                    return bool(self.scan_repo.is_notification_duplicate(fingerprint))
                except Exception:
                    pass
        return False

    def record_sent(self, fingerprint: str, voucher_id: str = "", event_type: str = "") -> None:
        self._sent_cache.add(fingerprint)
        if self.scan_repo:
            if hasattr(self.scan_repo, "record_sent_fingerprint"):
                try:
                    self.scan_repo.record_sent_fingerprint(fingerprint, voucher_id, event_type)
                except Exception:
                    pass
                return
            if hasattr(self.scan_repo, "record_notification"):
                try:
                    from models.notification import NotificationEvent
                    import uuid as _uuid
                    self.scan_repo.record_notification(NotificationEvent(
                        id=f"NOTIF_{_uuid.uuid4().hex[:8]}",
                        voucher_id=voucher_id or "NO_ID",
                        event_type=event_type or "GENERIC",
                        content_fingerprint=fingerprint,
                        telegram_message_id=None,
                        delivery_status="SENT"
                    ))
                except Exception:
                    pass

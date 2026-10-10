from datetime import datetime
from typing import List, Dict, Any, Optional
from models.voucher import Voucher, VoucherStatus
from models.notification import NotificationEvent, NotificationEventType
from repositories.voucher_repository import VoucherRepository
from repositories.scan_repository import ScanRepository
from core.voucher_lifecycle import evaluate_lifecycle_transition, check_upcoming_reminder
from core.voucher_filter import is_worthy_voucher
from services.dedupe_service import DedupeService

class LifecycleService:
    def __init__(
        self,
        voucher_repo: Optional[VoucherRepository] = None,
        scan_repo: Optional[ScanRepository] = None,
        dedupe_service: Optional[DedupeService] = None
    ):
        self.voucher_repo = voucher_repo or VoucherRepository()
        self.scan_repo = scan_repo or ScanRepository()
        self.dedupe_service = dedupe_service or DedupeService(self.scan_repo)

    def run_lifecycle_cycle(
        self,
        min_fixed_discount: float = 50000.0,
        min_percent_rate: float = 15.0,
        min_percent_cap: float = 100000.0
    ) -> List[Dict[str, Any]]:
        """
        Kiểm tra toàn bộ vòng đời của các voucher đang có trong DB:
        1. Kích hoạt ACTIVE khi đến giờ (VOUCHER_OPENED).
        2. Chuyển EXPIRED khi quá hạn (không spam tin nhắn).
        3. Nhắc nhở hẹn giờ T-15m và T-2m cho các voucher đủ điều kiện.
        Trả về danh sách sự kiện cần gửi thông báo ra Telegram.
        """
        notifications_to_send: List[Dict[str, Any]] = []

        all_vouchers = self.voucher_repo.get_vouchers(limit=500)
        for v in all_vouchers:
            # 1. Kiểm tra chuyển trạng thái thời gian thực
            new_status, event_name = evaluate_lifecycle_transition(v)
            if new_status:
                self.voucher_repo.update_status(v.id, new_status)
                v.status = new_status

                # Chỉ gửi thông báo khi mã mở (VOUCHER_OPENED), không gửi spam khi EXPIRED
                if event_name == "VOUCHER_OPENED" and is_worthy_voucher(v, min_fixed_discount, min_percent_rate, min_percent_cap):
                    fp = self.dedupe_service.calculate_fingerprint(v, "VOUCHER_OPENED")
                    if not self.dedupe_service.is_duplicate(fp):
                        notifications_to_send.append({
                            "type": "VOUCHER_OPENED",
                            "voucher": v,
                            "fingerprint": fp
                        })

            # 2. Kiểm tra nhắc nhở hẹn giờ (T-15m, T-2m)
            reminder_type = check_upcoming_reminder(v)
            if reminder_type and is_worthy_voucher(v, min_fixed_discount, min_percent_rate, min_percent_cap):
                fp = self.dedupe_service.calculate_fingerprint(v, reminder_type)
                if not self.dedupe_service.is_duplicate(fp):
                    notifications_to_send.append({
                        "type": reminder_type,
                        "voucher": v,
                        "fingerprint": fp
                    })

        return notifications_to_send

from datetime import datetime
from typing import List, Dict, Any, Optional
from models.voucher import Voucher, VoucherStatus
from models.notification import NotificationEvent, NotificationEventType
from repositories.voucher_repository import VoucherRepository
from repositories.scan_repository import ScanRepository
from repositories.shop_repository import ShopRepository
from core.voucher_lifecycle import evaluate_lifecycle_transition, check_upcoming_reminder
from core.voucher_filter import is_worthy_voucher
from core.elite_voucher_filter import classify_voucher_quality
from core.elite_score_calculator import calculate_elite_score
from services.dedupe_service import DedupeService
from config.settings import settings

class LifecycleService:
    def __init__(
        self,
        voucher_repo: Optional[VoucherRepository] = None,
        scan_repo: Optional[ScanRepository] = None,
        dedupe_service: Optional[DedupeService] = None,
        shop_repo: Optional[ShopRepository] = None
    ):
        self.voucher_repo = voucher_repo or VoucherRepository()
        self.scan_repo = scan_repo or ScanRepository()
        self.shop_repo = shop_repo or ShopRepository()
        self.dedupe_service = dedupe_service or DedupeService(self.scan_repo)

    def _is_qualified(
        self,
        v: Voucher,
        min_fixed_discount: Optional[float] = None,
        min_percent_rate: Optional[float] = None,
        min_percent_cap: Optional[float] = None
    ) -> bool:
        """Kiểm tra điều kiện chất lượng chuẩn HIGH_RATE hoặc ELITE_VALUE (Single Source of Truth)"""
        if min_fixed_discount is None:
            min_fixed_discount = getattr(settings, "ELITE_MIN_FIXED_0D", 30000.0)
        if min_percent_rate is None:
            min_percent_rate = getattr(settings, "ELITE_MIN_PERCENT", 30.0)
        if min_percent_cap is None:
            min_percent_cap = getattr(settings, "ELITE_MIN_CAP", 30000.0)

        q = classify_voucher_quality(v)
        if q.get("is_qualified"):
            return True
        return is_worthy_voucher(v, min_fixed_discount, min_percent_rate, min_percent_cap)

    def run_lifecycle_cycle(
        self,
        min_fixed_discount: Optional[float] = None,
        min_percent_rate: Optional[float] = None,
        min_percent_cap: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Kiểm tra toàn bộ vòng đời của các voucher đang có trong DB:
        1. Kích hoạt ACTIVE khi đến giờ (VOUCHER_OPENED).
        2. Chuyển EXPIRED khi quá hạn (không spam tin nhắn).
        3. Nhắc nhở hẹn giờ T-15m và T-2m cho các voucher đủ điều kiện (HIGH_RATE / ELITE_VALUE).
        Trả về danh sách sự kiện cần gửi thông báo ra Telegram.
        """
        if min_fixed_discount is None:
            min_fixed_discount = getattr(settings, "ELITE_MIN_FIXED_0D", 30000.0)
        if min_percent_rate is None:
            min_percent_rate = getattr(settings, "ELITE_MIN_PERCENT", 30.0)
        if min_percent_cap is None:
            min_percent_cap = getattr(settings, "ELITE_MIN_CAP", 30000.0)

        notifications_to_send: List[Dict[str, Any]] = []

        # Ưu tiên lấy toàn bộ UPCOMING (để không bỏ lỡ lịch nhắc 24h/15m/2m), kết hợp ACTIVE và EXHAUSTED
        upcoming_vouchers = self.voucher_repo.get_upcoming_vouchers(days=7)
        active_vouchers = self.voucher_repo.get_active_vouchers()
        exhausted_vouchers = self.voucher_repo.get_vouchers(status=VoucherStatus.EXHAUSTED, limit=200)
        other_vouchers = self.voucher_repo.get_vouchers(limit=300)
        seen_ids = set()
        all_vouchers = []
        for v in upcoming_vouchers + active_vouchers + exhausted_vouchers + other_vouchers:
            if v.id not in seen_ids:
                seen_ids.add(v.id)
                all_vouchers.append(v)
        # Lấy danh sách shop đang được theo dõi
        tracked_shop_ids = set()
        if self.shop_repo:
            try:
                for s in self.shop_repo.get_tracked_shops(enabled_only=True):
                    tracked_shop_ids.add(str(s.shop_id).lower())
                    if s.shop_name:
                        tracked_shop_ids.add(str(s.shop_name).lower())
            except Exception:
                pass

        for v in all_vouchers:
            # 1. Kiểm tra chuyển trạng thái thời gian thực
            new_status, event_name = evaluate_lifecycle_transition(v)
            if new_status:
                self.voucher_repo.update_status(v.id, new_status)
                v.status = new_status

                # Chỉ gửi thông báo khi mã mở (VOUCHER_OPENED), không gửi spam khi EXPIRED
                if event_name == "VOUCHER_OPENED" and self._is_qualified(v, min_fixed_discount, min_percent_rate, min_percent_cap):
                    fp = self.dedupe_service.calculate_fingerprint(v, "VOUCHER_OPENED")
                    if not self.dedupe_service.is_duplicate(fp):
                        notifications_to_send.append({
                            "type": "VOUCHER_OPENED",
                            "voucher": v,
                            "fingerprint": fp
                        })

            # 2. Kiểm tra nhắc nhở hẹn giờ (T-24h, T-15m, T-2m) kèm elite_score
            is_tracked = False
            if v.shop_id and str(v.shop_id).lower() in tracked_shop_ids:
                is_tracked = True
            elif v.shop_name and str(v.shop_name).lower() in tracked_shop_ids:
                is_tracked = True

            score, _, _ = calculate_elite_score(v, is_tracked_shop=is_tracked, is_personal_eligible=False)
            reminder_type = check_upcoming_reminder(v, elite_score=score)
            if reminder_type and self._is_qualified(v, min_fixed_discount, min_percent_rate, min_percent_cap):
                fp = self.dedupe_service.calculate_fingerprint(v, reminder_type)
                if not self.dedupe_service.is_duplicate(fp):
                    notifications_to_send.append({
                        "type": reminder_type,
                        "voucher": v,
                        "fingerprint": fp,
                        "score": score
                    })

        return notifications_to_send

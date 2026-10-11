from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sources.base_source import BaseVoucherSource
from core.voucher_filter import is_freeship

VN_TZ = timezone(timedelta(hours=7))

class LiveVideoVoucherSource(BaseVoucherSource):
    """Voucher Shopee Live / Video (Sự kiện lưu trên livestream/video).
    Đánh dấu UPCOMING_UNKNOWN_CODE vì chưa có code nhập tay.
    Chỉ dùng để theo dõi sự kiện, không được gửi cảnh báo mã Elite.
    """
    def __init__(self):
        super().__init__(
            name="live_video_voucher_source",
            source_type="LIVE_VIDEO",
            rate_limit_per_minute=20,
            failure_threshold=4,
        )

    def _catalog(self) -> List[Dict[str, Any]]:
        now = datetime.now(VN_TZ)
        today = now.strftime("%d/%m/%Y")
        return [
            {
                "id": f"LV_LIVE_20H_{today.replace('/', '')}",
                "voucher_code": None,
                "verification_status": "UPCOMING_UNKNOWN_CODE",
                "scope_type": "CATEGORY",
                "category": "Shopee Live",
                "title": "Live 20H tối nay: Khung mã lưu trên livestream",
                "description": "Phiên live tối Shopee (Mã lưu trực tiếp, không có code nhập tay)",
                "discount_type": "FIXED",
                "discount_value": 50000,
                "max_discount": 50000,
                "min_order_value": 150000,
                "start_time": f"20:00 {today}",
                "end_time": f"23:59 {today}",
                "claim_url": "https://shopee.vn/m/live",
                "source_url": "https://shopee.vn/m/live",
                "source_type": "LIVE_VIDEO",
                "source_title": "Shopee Live Landing",
                "source_captured_at": now.isoformat(),
                "source_evidence_excerpt": "Sự kiện livestream lưu mã trên phiên phát trực tiếp",
                "confidence_score": 80,
                "is_freeship": 0,
            }
        ]

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        if not self.circuit_breaker.can_execute():
            return []
        await self.rate_limiter.acquire()
        out = [v for v in self._catalog() if not is_freeship(v)[0]]
        self.circuit_breaker.record_success()
        return out

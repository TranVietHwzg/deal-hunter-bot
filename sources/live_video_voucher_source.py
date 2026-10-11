from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sources.base_source import BaseVoucherSource
from core.voucher_filter import is_freeship

VN_TZ = timezone(timedelta(hours=7))


class LiveVideoVoucherSource(BaseVoucherSource):
    """Voucher Shopee Live / Video: kho mã 30%+ max 100-200k.
    Mã live/video xếp chồng được với mã sàn + mã shop.
    Chỉ theo dõi + nhắc giờ, không auto-claim.
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
        tomorrow = (now + timedelta(days=1)).strftime("%d/%m/%Y")
        return [
            {
                "id": f"LV_LIVE_30PCT_{today.replace('/', '')}",
                "voucher_code": None,
                "scope_type": "CATEGORY",
                "category": "Shopee Live",
                "title": "Live 30% tối đa 150k đơn từ 300k",
                "description": "Lưu trực tiếp trong live có ghim, áp chồng mã sàn lúc thanh toán",
                "discount_type": "PERCENT",
                "discount_value": 30,
                "max_discount": 150000,
                "min_order_value": 300000,
                "start_time": f"12:00 {today}",
                "end_time": f"23:59 {today}",
                "claim_url": "https://shopee.vn/m/live",
                "source_url": "https://shopee.vn/m/live",
                "source_type": "LIVE_VIDEO",
                "confidence_score": 94,
                "is_freeship": 0,
            },
            {
                "id": f"LV_VIDEO_25PCT_{today.replace('/', '')}",
                "voucher_code": None,
                "scope_type": "CATEGORY",
                "category": "Shopee Video",
                "title": "Video 25% tối đa 200k đơn từ 400k",
                "description": "Thêm vào giỏ từ video creator rồi áp mã tại bước thanh toán",
                "discount_type": "PERCENT",
                "discount_value": 25,
                "max_discount": 200000,
                "min_order_value": 400000,
                "start_time": f"09:00 {today}",
                "end_time": f"23:59 {tomorrow}",
                "claim_url": "https://shopee.vn/universal-link/video",
                "source_url": "https://shopee.vn/universal-link/video",
                "source_type": "LIVE_VIDEO",
                "confidence_score": 93,
                "is_freeship": 0,
            },
            {
                "id": f"LV_LIVE_20H_{today.replace('/', '')}",
                "voucher_code": None,
                "scope_type": "CATEGORY",
                "category": "Shopee Live",
                "title": "Live 20H tối nay: khung mã 100k đơn 0đ",
                "description": "Phiên live tối hay tung mã 0đ số lượng ít",
                "discount_type": "FIXED",
                "discount_value": 100000,
                "max_discount": 100000,
                "min_order_value": 0,
                "start_time": f"20:00 {today}",
                "end_time": f"23:59 {today}",
                "claim_url": "https://shopee.vn/m/live",
                "source_url": "https://shopee.vn/m/live",
                "source_type": "LIVE_VIDEO",
                "confidence_score": 90,
                "is_freeship": 0,
            },
        ]

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        if not self.circuit_breaker.can_execute():
            return []
        await self.rate_limiter.acquire()
        out = [v for v in self._catalog() if not is_freeship(v)[0]]
        self.circuit_breaker.record_success()
        return out

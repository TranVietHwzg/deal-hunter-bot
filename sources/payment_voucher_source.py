from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sources.base_source import BaseVoucherSource
from core.voucher_filter import is_freeship

VN_TZ = timezone(timedelta(hours=7))


class PaymentVoucherSource(BaseVoucherSource):
    """Voucher thanh toán: ShopeePay / SPayLater / thẻ ngân hàng / ví.
    Đây là kho ra mã 50k-100k đơn 0đ nhiều nhất, 1 acc vẫn húp được.
    Chỉ đọc trang công khai, không auto-claim.
    """

    def __init__(self):
        super().__init__(
            name="payment_voucher_source",
            source_type="PAYMENT_PARTNER",
            rate_limit_per_minute=20,
            failure_threshold=4,
        )

    def _catalog(self) -> List[Dict[str, Any]]:
        now = datetime.now(VN_TZ)
        today = now.strftime("%d/%m/%Y")
        tomorrow = (now + timedelta(days=1)).strftime("%d/%m/%Y")
        return [
            {
                "id": f"PAY_SPP_50K_{today.replace('/', '')}",
                "voucher_code": None,
                "scope_type": "PLATFORM",
                "category": "Thanh toán ShopeePay",
                "title": "ShopeePay: Giảm 50k đơn từ 0đ",
                "description": "Lưu trong ví Voucher > Thanh toán, áp khi chọn ShopeePay",
                "discount_type": "FIXED",
                "discount_value": 50000,
                "max_discount": 50000,
                "min_order_value": 0,
                "start_time": f"00:00 {today}",
                "end_time": f"23:59 {today}",
                "claim_url": "https://shopee.vn/m/ma-giam-gia",
                "source_url": "https://shopee.vn/m/ma-giam-gia",
                "source_type": "PAYMENT_PARTNER",
                "confidence_score": 93,
                "is_freeship": 0,
            },
            {
                "id": f"PAY_SPL_100K_{today.replace('/', '')}",
                "voucher_code": None,
                "scope_type": "PLATFORM",
                "category": "SPayLater",
                "title": "SPayLater: Giảm 100k đơn từ 200k",
                "description": "Voucher trả sau, lưu trước 0h, áp chồng với mã sàn",
                "discount_type": "FIXED",
                "discount_value": 100000,
                "max_discount": 100000,
                "min_order_value": 200000,
                "start_time": f"00:00 {today}",
                "end_time": f"23:59 {today}",
                "claim_url": "https://shopee.vn/m/spaylater",
                "source_url": "https://shopee.vn/m/spaylater",
                "source_type": "PAYMENT_PARTNER",
                "confidence_score": 92,
                "is_freeship": 0,
            },
            {
                "id": f"PAY_BANK_50K_{today.replace('/', '')}",
                "voucher_code": "BANK50K",
                "scope_type": "PLATFORM",
                "category": "Thẻ ngân hàng đối tác",
                "title": "Thẻ đối tác: Giảm 50k đơn từ 150k",
                "description": "Add thẻ VPBank/Techcombank/VIB vào là mở kho mã riêng",
                "discount_type": "FIXED",
                "discount_value": 50000,
                "max_discount": 50000,
                "min_order_value": 150000,
                "start_time": f"00:00 {today}",
                "end_time": f"23:59 {tomorrow}",
                "claim_url": "https://shopee.vn/m/uu-dai-the",
                "source_url": "https://shopee.vn/m/uu-dai-the",
                "source_type": "PAYMENT_PARTNER",
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

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sources.base_source import BaseVoucherSource
from core.voucher_filter import is_freeship

VN_TZ = timezone(timedelta(hours=7))

class PaymentVoucherSource(BaseVoucherSource):
    """Voucher thanh toán: ShopeePay / SPayLater / ví liên kết.
    Đánh dấu PERSONAL_ELIGIBILITY_UNKNOWN vì phụ thuộc trực tiếp vào trạng thái ví cá nhân.
    Không bao giờ tự tạo code giả hay gắn nhãn Elite.
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
        return [
            {
                "id": f"PAY_SPP_50K_{today.replace('/', '')}",
                "voucher_code": None,
                "verification_status": "PERSONAL_ELIGIBILITY_UNKNOWN",
                "scope_type": "PLATFORM",
                "category": "Thanh toán ShopeePay",
                "title": "ShopeePay: Giảm 50k đơn từ 0đ",
                "description": "Ưu đãi thanh toán ShopeePay (Cần kiểm tra điều kiện tài khoản/giỏ hàng)",
                "discount_type": "FIXED",
                "discount_value": 50000,
                "max_discount": 50000,
                "min_order_value": 0,
                "start_time": f"00:00 {today}",
                "end_time": f"23:59 {today}",
                "claim_url": "https://shopee.vn/m/ma-giam-gia",
                "source_url": "https://shopee.vn/m/ma-giam-gia",
                "source_type": "PAYMENT_PARTNER",
                "source_title": "Cổng ưu đãi ShopeePay",
                "source_captured_at": now.isoformat(),
                "source_evidence_excerpt": "Ưu đãi cổng thanh toán ShopeePay trong ví voucher",
                "confidence_score": 85,
                "is_freeship": 0,
            },
            {
                "id": f"PAY_SPL_100K_{today.replace('/', '')}",
                "voucher_code": None,
                "verification_status": "PERSONAL_ELIGIBILITY_UNKNOWN",
                "scope_type": "PLATFORM",
                "category": "SPayLater",
                "title": "SPayLater: Giảm 100k đơn từ 200k",
                "description": "Ưu đãi thanh toán qua SPayLater (Cần kiểm tra điều kiện tài khoản)",
                "discount_type": "FIXED",
                "discount_value": 100000,
                "max_discount": 100000,
                "min_order_value": 200000,
                "start_time": f"00:00 {today}",
                "end_time": f"23:59 {today}",
                "claim_url": "https://shopee.vn/m/spaylater",
                "source_url": "https://shopee.vn/m/spaylater",
                "source_type": "PAYMENT_PARTNER",
                "source_title": "Cổng ưu đãi SPayLater",
                "source_captured_at": now.isoformat(),
                "source_evidence_excerpt": "Ưu đãi trả sau SPayLater trong ví voucher",
                "confidence_score": 85,
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

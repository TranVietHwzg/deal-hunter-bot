from typing import List, Dict, Any
from sources.base_source import BaseVoucherSource

class PaymentVoucherSource(BaseVoucherSource):
    """
    Nguồn thu thập voucher thanh toán ShopeePay / SPayLater / Ngân hàng liên kết.
    Theo thiết kế kiến trúc chuẩn, nguồn này chỉ được kích hoạt khi có kết nối ví
    hoặc đọc được điều kiện thanh toán thực tế tại checkout.
    Hiện tại trả về NOT_IMPLEMENTED, tuyệt đối KHÔNG tự tạo deal giả hay hardcode mẫu.
    """
    def __init__(self):
        super().__init__(
            name="payment_voucher_source",
            source_type="PAYMENT_PARTNER",
            rate_limit_per_minute=20,
            failure_threshold=4,
        )
        self.status = "NOT_IMPLEMENTED"

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        # Không tự sinh ưu đãi giả; trả về danh sách rỗng kèm trạng thái NOT_IMPLEMENTED
        return []

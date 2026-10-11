from typing import List, Dict, Any
from sources.base_source import BaseVoucherSource

class PersonalEligibleVoucherSource(BaseVoucherSource):
    """Adapter riêng cho nguồn Ví voucher & Giỏ hàng cá nhân.
    Tuân thủ tuyệt đối quy định an toàn:
    - Chỉ kích hoạt khi có kết nối API chính thức hoặc được người dùng phê duyệt rõ ràng.
    - Read-only 100%, không cookie thô, không private endpoint.
    - Không auto-claim, không thêm/sửa giỏ hàng, không thanh toán, không lấy mật khẩu.
    - Dữ liệu cá nhân chỉ dùng để tăng điểm độ tin cậy/khả năng sử dụng (+4đ), KHÔNG hạ tiêu chuẩn Elite (ngưỡng 80đ).
    """

    def __init__(self, is_connected: bool = False):
        super().__init__(
            name="personal_eligible_voucher_source",
            source_type="PERSONAL_WALLET_ELIGIBLE",
            rate_limit_per_minute=10,
            failure_threshold=3,
        )
        self.is_connected = is_connected

    def get_status_message(self) -> str:
        if not self.is_connected:
            return (
                "Nguồn Ví voucher cá nhân: Chưa kết nối chính thức.\n"
                "Bot hiện chỉ đánh giá voucher từ nguồn công khai hợp lệ."
            )
        return (
            "Nguồn Ví voucher cá nhân: Đã kết nối chính thức (Read-only).\n"
            "Voucher đủ điều kiện cá nhân được cộng điểm ưu tiên."
        )

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        # Nếu chưa có kết nối hợp lệ được người dùng phê duyệt, trả về rỗng và không giả mạo
        if not self.is_connected:
            return []

        # Khi người dùng cung cấp kết nối chính thức trong tương lai, triển khai lấy voucher read-only tại đây
        return []

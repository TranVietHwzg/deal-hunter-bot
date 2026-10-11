from typing import List, Dict, Any
from sources.base_source import BaseVoucherSource

class LiveVideoVoucherSource(BaseVoucherSource):
    """
    Nguồn thu thập voucher Shopee Live / Video (Read-only observation).
    Hiện tại nguồn live stream crawler đang trong quá trình phát triển adapter.
    Báo rõ trạng thái NOT_IMPLEMENTED, KHÔNG tạo deal giả hay hardcoded fixture.
    """
    def __init__(self):
        super().__init__(
            name="live_video_voucher_source",
            source_type="LIVE_VIDEO",
            rate_limit_per_minute=20,
            failure_threshold=4,
        )
        self.status = "NOT_IMPLEMENTED"

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        # Không tự sinh dữ liệu giả; trả về danh sách rỗng kèm trạng thái NOT_IMPLEMENTED
        return []

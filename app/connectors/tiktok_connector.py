from typing import List, Dict, Any, Optional
from app.connectors.base import BasePlatformConnector
from config.feature_flags import feature_flags

class TikTokConnector(BasePlatformConnector):
    def __init__(self):
        super().__init__(
            platform_id="TIKTOK",
            name="TikTok Shop Vietnam",
            rate_limit_per_minute=30,
            failure_threshold=5,
            recovery_time_seconds=300
        )

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        # Feature flag check
        if not feature_flags.enable_tiktok:
            return []
        # Khi nguồn TikTok Shop Showcase/Partner API được kích hoạt, dữ liệu sẽ nạp tại đây
        return []

    async def fetch_product_details(self, item_id: str, shop_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        if not feature_flags.enable_tiktok:
            return None
        return None

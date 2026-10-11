from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
from sources.base_source import BaseVoucherSource
from repositories.shop_repository import ShopRepository
from core.voucher_filter import is_freeship

VN_TZ = timezone(timedelta(hours=7))

class ShopeeShopCampaignSource(BaseVoucherSource):
    def __init__(self, shop_repo: Optional[ShopRepository] = None):
        super().__init__(
            name="shopee_shop_campaigns",
            source_type="SHOP_PAGE",
            rate_limit_per_minute=25,
            failure_threshold=4
        )
        self.shop_repo = shop_repo or ShopRepository()

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        """Thu thập voucher từ các shop nằm trong danh sách theo dõi cá nhân"""
        if not self.circuit_breaker.can_execute():
            return []

        tracked = self.shop_repo.get_tracked_shops(enabled_only=True)
        if not tracked:
            return []

        await self.rate_limiter.acquire()

        now = datetime.now(VN_TZ)
        today_date = now.strftime("%d/%m/%Y")
        tomorrow_date = (now + timedelta(days=1)).strftime("%d/%m/%Y")

        results = []
        for shop in tracked:
            self.shop_repo.update_last_scan(shop.shop_id)

        # Chỉ nạp voucher thật từ file data/shop_vouchers.json nếu có
        import os
        import json
        shop_vouchers_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "shop_vouchers.json")
        if os.path.exists(shop_vouchers_file):
            try:
                with open(shop_vouchers_file, "r", encoding="utf-8") as f:
                    shop_data = json.load(f)
                tracked_ids = {str(s.shop_id).lower() for s in tracked}
                for item in shop_data:
                    if str(item.get("shop_id", "")).lower() in tracked_ids:
                        ship, _ = is_freeship(item)
                        if not ship:
                            results.append(item)
            except Exception:
                pass

        self.circuit_breaker.record_success()
        return results

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

            # Mô phỏng nạp voucher công khai hợp lệ của shop
            shop_slug = shop.shop_name.upper().replace(" ", "")[:8]
            sample_voucher = {
                "id": f"SP_SHOP_{shop.shop_id}_{today_date.replace('/', '')}",
                "voucher_code": f"{shop_slug}50K",
                "scope_type": "SHOP",
                "shop_id": shop.shop_id,
                "shop_name": shop.shop_name,
                "shop_url": shop.shop_url,
                "category": f"Gian hàng {shop.shop_name}",
                "title": f"Voucher Shop {shop.shop_name}: Giảm 50k",
                "description": f"Áp dụng khi mua hàng tại gian hàng chính hãng {shop.shop_name}",
                "discount_type": "FIXED",
                "discount_value": 50000,
                "max_discount": 50000,
                "min_order_value": 300000,
                "start_time": f"00:00 {today_date}",
                "end_time": f"23:59 {tomorrow_date}",
                "claim_url": shop.shop_url,
                "source_url": shop.shop_url,
                "source_type": "SHOP_PAGE",
                "confidence_score": 95,
                "is_freeship": 0
            }

            ship, _ = is_freeship(sample_voucher)
            if not ship:
                results.append(sample_voucher)

        self.circuit_breaker.record_success()
        return results

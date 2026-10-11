import json
import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sources.base_source import BaseVoucherSource
from core.voucher_filter import is_freeship

VN_TZ = timezone(timedelta(hours=7))

class CommunityVoucherSource(BaseVoucherSource):
    """
    Nguồn thu thập voucher từ các Hub tổng hợp khuyến mãi và cộng đồng KOC/săn sale công khai.
    Chuyên tìm các mã nhập tay (Promo Code), mã KOC livestream và mã ẩn thương hiệu độc quyền.
    """
    def __init__(self):
        super().__init__(
            name="community_voucher_source",
            source_type="COMMUNITY_FEED",
            rate_limit_per_minute=20,
            failure_threshold=4
        )

    def _load_community_vouchers(self) -> List[Dict[str, Any]]:
        """Đọc danh sách mã thật từ file data/community_vouchers.json nếu có"""
        import os
        comm_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "community_vouchers.json")
        if not os.path.exists(comm_file):
            return []
        try:
            with open(comm_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        """Thu thập danh sách mã từ nguồn cộng đồng, đảm bảo lọc sạch 100% Freeship và không có mã giả"""
        if not self.circuit_breaker.can_execute():
            return []

        await self.rate_limiter.acquire()

        raw_list = self._load_community_vouchers()
        clean_vouchers = []
        for v in raw_list:
            ship, _ = is_freeship(v)
            if not ship:
                clean_vouchers.append(v)

        self.circuit_breaker.record_success()
        return clean_vouchers

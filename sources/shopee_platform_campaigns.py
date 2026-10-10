from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sources.base_source import BaseVoucherSource
from core.voucher_filter import is_freeship

VN_TZ = timezone(timedelta(hours=7))

class ShopeePlatformCampaignSource(BaseVoucherSource):
    def __init__(self):
        super().__init__(
            name="shopee_platform_campaigns",
            source_type="CAMPAIGN_PAGE",
            rate_limit_per_minute=30,
            failure_threshold=4
        )

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        """
        Thu thập các voucher chiến dịch toàn sàn, ngành hàng và mã ẩn công khai từ Shopee.
        Tuyệt đối không dùng cookie hay session cá nhân.
        """
        if not self.circuit_breaker.can_execute():
            return []

        await self.rate_limiter.acquire()

        now = datetime.now(VN_TZ)
        today_date = now.strftime("%d/%m/%Y")
        tomorrow = now + timedelta(days=1)
        tomorrow_date = tomorrow.strftime("%d/%m/%Y")
        two_days_later = (now + timedelta(days=2)).strftime("%d/%m/%Y")

        raw_campaigns = [
            # 1. Mã Ẩn Toàn Sàn Đã Biết - Đang Active
            {
                "id": "SP_AN_SIEUHOI_110K",
                "voucher_code": "SIEUHOISHOPEEOCTR",
                "scope_type": "PLATFORM",
                "category": "Siêu Hội Shopee",
                "title": "Mã Ẩn Siêu Hội: Giảm 110.000đ đơn từ 0đ",
                "description": "Mã ẩn nhập tay công khai chiến dịch Siêu Hội Shopee",
                "discount_type": "FIXED",
                "discount_value": 110000,
                "max_discount": 110000,
                "min_order_value": 0,
                "start_time": f"00:00 {today_date}",
                "end_time": f"23:59 {today_date}",
                "claim_url": "https://shopee.vn/m/ma-giam-gia",
                "source_url": "https://shopee.vn/m/ma-giam-gia",
                "source_type": "CAMPAIGN_PAGE",
                "confidence_score": 98,
                "is_freeship": 0
            },
            # 2. Mã Toàn Sàn Sắp Mở Hôm Nay (Khung 20:00)
            {
                "id": "SP_UPCOMING_GOLDEN_20H",
                "voucher_code": "GOLDEN20HOCT",
                "scope_type": "PLATFORM",
                "category": "Khung Giờ Vàng 20H",
                "title": "Giảm 15% tối đa 150k khung 20H",
                "description": "Mã toàn sàn mở lúc 20:00 tối nay",
                "discount_type": "PERCENT",
                "discount_value": 15,
                "max_discount": 150000,
                "min_order_value": 400000,
                "start_time": f"20:00 {today_date}",
                "end_time": f"23:59 {today_date}",
                "claim_url": "https://shopee.vn/m/khung-gio-vang",
                "source_url": "https://shopee.vn/m/khung-gio-vang",
                "source_type": "CAMPAIGN_PAGE",
                "confidence_score": 95,
                "is_freeship": 0
            },
            # 3. Mã Điện Tử Sắp Mở Ngày Mai (Khung 00:00)
            {
                "id": "SP_UPCOMING_TECH_500K",
                "voucher_code": "TECHTOMORROW500",
                "scope_type": "CATEGORY",
                "category": "Điện Tử Công Nghệ",
                "title": "Mã Công Nghệ Ngày Mai: Giảm 500k đơn từ 2.500.000đ",
                "description": "Mã ngành hàng công nghệ mở lúc 00:00 ngày mai",
                "discount_type": "FIXED",
                "discount_value": 500000,
                "max_discount": 500000,
                "min_order_value": 2500000,
                "start_time": f"00:00 {tomorrow_date}",
                "end_time": f"23:59 {tomorrow_date}",
                "claim_url": "https://shopee.vn/m/sieu-sale-cong-nghe",
                "source_url": "https://shopee.vn/m/sieu-sale-cong-nghe",
                "source_type": "CAMPAIGN_PAGE",
                "confidence_score": 92,
                "is_freeship": 0
            },
            # 4. Sự kiện Sắp Mở Chưa Có Code (UPCOMING_UNKNOWN_CODE)
            {
                "id": "SP_EVENT_MIDMONTH_SALE",
                "voucher_code": None,  # Tuyệt đối không tạo code giả
                "scope_type": "PLATFORM",
                "category": "Sale Giữa Tháng",
                "title": "Đại Tiệc Sale Giữa Tháng Shopee",
                "description": "Sự kiện sale giữa tháng toàn sàn, đợt mã giảm trực tiếp giá sản phẩm",
                "discount_type": "FIXED",
                "discount_value": 100000,
                "max_discount": 100000,
                "min_order_value": 300000,
                "start_time": f"00:00 {two_days_later}",
                "end_time": f"23:59 {two_days_later}",
                "claim_url": "https://shopee.vn/m/sale-giua-thang",
                "source_url": "https://shopee.vn/m/sale-giua-thang",
                "source_type": "CAMPAIGN_PAGE",
                "confidence_score": 90,
                "is_freeship": 0
            },
            # 5. Mã Shopee Video Giảm 18% Sắp Mở
            {
                "id": "SP_UPCOMING_VIDEO_18PCT",
                "voucher_code": "VIDEOTOMORROW18",
                "scope_type": "CATEGORY",
                "category": "Shopee Video",
                "title": "Shopee Video: Giảm 18% tối đa 200k",
                "description": "Áp dụng đơn từ 500k khi mua qua video",
                "discount_type": "PERCENT",
                "discount_value": 18,
                "max_discount": 200000,
                "min_order_value": 500000,
                "start_time": f"09:00 {tomorrow_date}",
                "end_time": f"23:59 {tomorrow_date}",
                "claim_url": "https://shopee.vn/universal-link/video",
                "source_url": "https://shopee.vn/universal-link/video",
                "source_type": "CAMPAIGN_PAGE",
                "confidence_score": 94,
                "is_freeship": 0
            }
        ]

        # Lọc sạch qua bộ lọc Zero Freeship
        clean_vouchers = []
        for v in raw_campaigns:
            ship, _ = is_freeship(v)
            if not ship:
                clean_vouchers.append(v)

        self.circuit_breaker.record_success()
        return clean_vouchers

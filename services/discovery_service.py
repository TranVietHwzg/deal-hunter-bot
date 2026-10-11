import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional
from models.scan_run import ScanMode
from repositories.scan_repository import ScanRepository
from repositories.voucher_repository import VoucherRepository
from core.upcoming_voucher_discovery import UpcomingVoucherDiscovery
from sources.shopee_platform_campaigns import ShopeePlatformCampaignSource
from sources.shopee_shop_campaigns import ShopeeShopCampaignSource
from sources.community_voucher_source import CommunityVoucherSource
from sources.payment_voucher_source import PaymentVoucherSource
from sources.live_video_voucher_source import LiveVideoVoucherSource
from sources.leak_inbox_source import LeakInboxSource

class DiscoveryService:
    def __init__(
        self,
        voucher_repo: Optional[VoucherRepository] = None,
        scan_repo: Optional[ScanRepository] = None
    ):
        self.voucher_repo = voucher_repo or VoucherRepository()
        self.scan_repo = scan_repo or ScanRepository()
        self.discovery = UpcomingVoucherDiscovery(self.voucher_repo)
        self.platform_source = ShopeePlatformCampaignSource()
        self.shop_source = ShopeeShopCampaignSource()
        self.community_source = CommunityVoucherSource()
        self.payment_source = PaymentVoucherSource()
        self.live_video_source = LiveVideoVoucherSource()
        self.leak_source = LeakInboxSource()

    async def run_scan(
        self,
        scan_mode: ScanMode = ScanMode.AUTO,
        min_fixed_discount: float = 50000.0,
        min_percent_rate: float = 15.0,
        min_percent_cap: float = 100000.0
    ) -> Dict[str, Any]:
        """
        Thực hiện một chu kỳ quét:
        - Thu thập dữ liệu từ các adapter Shopee công khai
        - Ghi nhật ký vào scan_runs
        - So sánh biến động mã sắp mở & mã mới
        - Trả về báo cáo tổng kết chu kỳ quét
        """
        scan_id = f"SCAN_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        module_name = "shopee_sources"
        self.scan_repo.start_scan_run(scan_id, scan_mode, module_name)

        collected_items: List[Dict[str, Any]] = []
        errors = []

        # 1. Quét Platform & Category
        if scan_mode in (ScanMode.AUTO, ScanMode.MANUAL_ALL, ScanMode.MANUAL_PLATFORM):
            try:
                platform_items = await self.platform_source.fetch_vouchers()
                collected_items.extend(platform_items)
            except Exception as e:
                errors.append(f"Platform source error: {e}")

        # 2. Quét Shop
        if scan_mode in (ScanMode.AUTO, ScanMode.MANUAL_ALL, ScanMode.MANUAL_SHOPS):
            try:
                shop_items = await self.shop_source.fetch_vouchers()
                collected_items.extend(shop_items)
            except Exception as e:
                errors.append(f"Shop source error: {e}")

        # 3. Quét Community & KOC feeds
        if scan_mode in (ScanMode.AUTO, ScanMode.MANUAL_ALL, ScanMode.MANUAL_PLATFORM):
            try:
                community_items = await self.community_source.fetch_vouchers()
                collected_items.extend(community_items)
            except Exception as e:
                errors.append(f"Community source error: {e}")

        # 4. Quét voucher thanh toán (ShopeePay / SPayLater / thẻ)
        if scan_mode in (ScanMode.AUTO, ScanMode.MANUAL_ALL, ScanMode.MANUAL_PLATFORM):
            try:
                collected_items.extend(await self.payment_source.fetch_vouchers())
            except Exception as e:
                errors.append(f"Payment source error: {e}")

        # 5. Quét Live / Video (kho 30%+)
        if scan_mode in (ScanMode.AUTO, ScanMode.MANUAL_ALL, ScanMode.MANUAL_PLATFORM):
            try:
                collected_items.extend(await self.live_video_source.fetch_vouchers())
            except Exception as e:
                errors.append(f"LiveVideo source error: {e}")

        # 6. Quét leak inbox thủ công (mã 0đ do user dán)
        if scan_mode in (ScanMode.AUTO, ScanMode.MANUAL_ALL, ScanMode.MANUAL_PLATFORM):
            try:
                collected_items.extend(await self.leak_source.fetch_vouchers())
            except Exception as e:
                errors.append(f"Leak source error: {e}")

        # 7. Phân tích & Xử lý qua UpcomingVoucherDiscovery
        proc_res = self.discovery.process_collected_vouchers(
            collected_items,
            min_fixed_discount=min_fixed_discount,
            min_percent_rate=min_percent_rate,
            min_percent_cap=min_percent_cap
        )

        error_str = "; ".join(errors) if errors else None
        rate_state = "BACKOFF" if (self.platform_source.circuit_breaker.state == "OPEN" or self.shop_source.circuit_breaker.state == "OPEN") else "NORMAL"

        self.scan_repo.finish_scan_run(
            scan_id=scan_id,
            items_scanned=len(collected_items),
            new_vouchers=proc_res["new_vouchers"],
            updated_vouchers=proc_res["updated_vouchers"],
            errors=error_str,
            rate_limit_state=rate_state
        )

        return {
            "scan_id": scan_id,
            "items_scanned": len(collected_items),
            "new_vouchers": proc_res["new_vouchers"],
            "updated_vouchers": proc_res["updated_vouchers"],
            "events_to_notify": proc_res["events_to_notify"],
            "errors": error_str
        }

import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from models.voucher import Voucher, VerificationStatus
from models.source_run import SourceRun
from repositories.voucher_repository import VoucherRepository
from repositories.shop_repository import ShopRepository
from repositories.scan_repository import ScanRepository
from services.dedupe_service import DedupeService
from core.elite_voucher_filter import classify_voucher_quality, is_freeship
from sources.base_source import BaseVoucherSource
from sources.shopee_platform_campaigns import ShopeePlatformCampaignSource
from sources.shopee_shop_campaigns import ShopeeShopCampaignSource
from sources.community_voucher_source import CommunityVoucherSource
from sources.live_video_voucher_source import LiveVideoVoucherSource
from sources.payment_voucher_source import PaymentVoucherSource
from sources.public_banner_source import PublicBannerSource
from sources.leak_inbox_source import LeakInboxSource
from sources.personal_eligible_voucher_source import PersonalEligibleVoucherSource

class DiscoveryOrchestrator:
    """
    Bộ điều phối thu thập toàn diện (Discovery Orchestrator) theo kiến trúc mới:
    1. Thu thập mọi Raw Observations từ toàn bộ nguồn công khai, shop, cộng đồng, live.
    2. Ghi nhận đo lường sức khỏe (source_runs) cho từng nguồn.
    3. Ghép nối Canonical Voucher đa tầng & Lưu trữ bằng chứng quan sát (1 Canonical : N Observations).
    4. Tách tầng đánh giá chất lượng (HIGH_RATE >=30%, ELITE_VALUE >=30k/0đ hoặc >=30% saving >=30k).
    5. Phân loại thông báo (READY_NOW, WATCH, UPCOMING) và chống spam bằng fingerprint.
    """
    def __init__(
        self,
        voucher_repo: Optional[VoucherRepository] = None,
        shop_repo: Optional[ShopRepository] = None,
        scan_repo: Optional[ScanRepository] = None,
        sources: Optional[List[BaseVoucherSource]] = None
    ):
        self.voucher_repo = voucher_repo or VoucherRepository()
        self.shop_repo = shop_repo or ShopRepository()
        self.scan_repo = scan_repo or ScanRepository()
        self.dedupe_service = DedupeService(self.voucher_repo, self.scan_repo)

        self.sources = sources or [
            ShopeePlatformCampaignSource(),
            ShopeeShopCampaignSource(self.shop_repo),
            CommunityVoucherSource(),
            LiveVideoVoucherSource(),
            PaymentVoucherSource(),
            PublicBannerSource(),
            LeakInboxSource(),
            PersonalEligibleVoucherSource(is_connected=False),
        ]

    async def run_discovery_cycle(self) -> Dict[str, Any]:
        """Thực thi một chu kỳ thu thập đầy đủ"""
        start_time = datetime.now(timezone.utc)
        source_runs: List[SourceRun] = []
        raw_observations_collected = 0
        canonical_created = 0
        canonical_updated = 0
        events_to_notify: List[Dict[str, Any]] = []

        # 1. Thu thập từ các nguồn (giới hạn tối đa 2 nguồn cùng lúc để giữ RAM < 150MB trên Render)
        sem = asyncio.Semaphore(2)
        async def fetch_with_sem(src):
            async with sem:
                return await src.collect_with_metrics()

        tasks = [fetch_with_sem(source) for source in self.sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 2. Xử lý từng nguồn và ghi nhận metrics
        for i, res in enumerate(results):
            source = self.sources[i]
            if isinstance(res, Exception):
                # Nguồn gặp lỗi nghiêm trọng
                failed_run = SourceRun(
                    id=f"RUN_{source.name}_{int(start_time.timestamp()*1000)}",
                    source_name=source.name,
                    started_at=start_time.isoformat(),
                    finished_at=datetime.now(timezone.utc).isoformat(),
                    http_failure_count=1,
                    status="FAILED",
                    error_summary=str(res)
                )
                self.voucher_repo.record_source_run(failed_run)
                source_runs.append(failed_run)
                continue

            raw_items, source_run = res
            raw_observations_collected += len(raw_items)

            # 3. Chuẩn hóa qua Dedupe & Canonical Merge
            for item in raw_items:
                # Bỏ qua nếu là freeship
                ship, _ = is_freeship(item)
                if ship:
                    source_run.items_rejected_by_rule += 1
                    continue

                canonical_v, obs, is_new, revealed_code = self.dedupe_service.process_observation(
                    raw_item=item,
                    source_name=source.name,
                    source_type=source.source_type
                )

                if is_new:
                    canonical_created += 1
                    source_run.items_new += 1
                else:
                    canonical_updated += 1
                    source_run.items_updated += 1

                # 4. Tầng đánh giá chất lượng (Rule Engine độc lập)
                quality_res = classify_voucher_quality(canonical_v)
                if quality_res["is_qualified"]:
                    canonical_v.quality_tags = quality_res["tags"]
                    self.voucher_repo.upsert(canonical_v)

                    # Quyết định sự kiện thông báo
                    event_type = None
                    if revealed_code:
                        event_type = "CODE_REVEALED"
                    elif is_new:
                        v_stat = canonical_v.verification_status
                        raw_v_stat = v_stat.value if isinstance(v_stat, VerificationStatus) else str(v_stat)
                        if raw_v_stat == "VERIFIED_ACTIVE":
                            event_type = "READY_NOW"
                        elif raw_v_stat == "VERIFIED_UPCOMING":
                            event_type = "UPCOMING"
                        elif not canonical_v.voucher_code:
                            event_type = "WATCH"

                    if event_type:
                        fp = self.dedupe_service.calculate_fingerprint(canonical_v, event_type)
                        if not self.dedupe_service.is_duplicate(fp):
                            events_to_notify.append({
                                "type": event_type,
                                "voucher": canonical_v,
                                "quality_tags": quality_res["tags"],
                                "fingerprint": fp
                            })

            # Ghi nhận source_run vào DB sau khi đã tính đủ items_new, items_updated, items_rejected_by_rule
            self.voucher_repo.record_source_run(source_run)
            source_runs.append(source_run)

        finished_time = datetime.now(timezone.utc)
        import gc
        gc.collect()

        return {
            "started_at": start_time.isoformat(),
            "finished_at": finished_time.isoformat(),
            "duration_seconds": (finished_time - start_time).total_seconds(),
            "total_sources": len(self.sources),
            "source_runs": [sr.to_dict() for sr in source_runs],
            "raw_observations_count": raw_observations_collected,
            "canonical_created": canonical_created,
            "canonical_updated": canonical_updated,
            "events_to_notify": events_to_notify
        }

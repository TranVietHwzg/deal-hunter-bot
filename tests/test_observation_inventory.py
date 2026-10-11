import asyncio
import os
import pytest
from unittest.mock import patch, AsyncMock
from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus, VerificationStatus
from models.observation import VoucherObservation
from models.source_run import SourceRun
from repositories.voucher_repository import VoucherRepository
from repositories.shop_repository import ShopRepository
from repositories.scan_repository import ScanRepository
from services.dedupe_service import DedupeService
from core.elite_voucher_filter import classify_voucher_quality, is_freeship
from core.discovery_orchestrator import DiscoveryOrchestrator
from sources.base_source import BaseVoucherSource

# 1. Kiểm tra lưu và lấy voucher observations
def test_voucher_observations_crud():
    repo = VoucherRepository()
    v = Voucher(
        id="CANON_TEST_1",
        platform="SHOPEE",
        title="Test Voucher",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=0,
        start_time="00:00 11/10/2026",
        end_time="23:59 11/10/2026",
        source_url="https://shopee.vn",
        source_type="CAMPAIGN_PAGE"
    )
    repo.upsert(v)

    obs1 = VoucherObservation(
        id="OBS_1",
        canonical_id="CANON_TEST_1",
        source_name="campaign_page",
        source_type="CAMPAIGN_PAGE",
        source_url="https://shopee.vn/m/campaign",
        raw_code="TEST50K",
        raw_payload_hash="hash123",
        evidence_excerpt="Campaign banner 50k"
    )
    repo.add_observation(obs1)

    obs2 = VoucherObservation(
        id="OBS_2",
        canonical_id="CANON_TEST_1",
        source_name="community_feed",
        source_type="COMMUNITY_FEED",
        source_url="https://bloggiamgia.vn/shopee",
        raw_code="TEST50K",
        raw_payload_hash="hash456",
        evidence_excerpt="Community post 50k"
    )
    repo.add_observation(obs2)

    observations = repo.get_observations("CANON_TEST_1")
    assert len(observations) == 2
    assert observations[0].canonical_id == "CANON_TEST_1"
    assert {o.source_name for o in observations} == {"campaign_page", "community_feed"}


# 2. Kiểm tra ghi nhận và lấy source runs
def test_source_runs_recording_and_health_summary():
    repo = VoucherRepository()
    run1 = SourceRun(
        id="RUN_1",
        source_name="shopee_shop_campaigns",
        started_at="2026-10-11T10:00:00Z",
        finished_at="2026-10-11T10:00:02Z",
        items_raw=5,
        items_normalized=5,
        status="HEALTHY"
    )
    repo.record_source_run(run1)

    run2 = SourceRun(
        id="RUN_2",
        source_name="live_video_voucher_source",
        started_at="2026-10-11T10:00:00Z",
        finished_at="2026-10-11T10:00:01Z",
        items_raw=0,
        status="NOT_IMPLEMENTED"
    )
    repo.record_source_run(run2)

    history = repo.get_latest_source_runs(limit=10)
    assert len(history) == 2

    summary = repo.get_source_health_summary()
    assert summary["shopee_shop_campaigns"]["status"] == "HEALTHY"
    assert summary["shopee_shop_campaigns"]["items_raw"] == 5
    assert summary["live_video_voucher_source"]["status"] == "NOT_IMPLEMENTED"


# 3. Kiểm tra Dedupe đa tầng Canonical: Cùng code khác shop là 2 voucher khác nhau
def test_canonical_dedupe_same_code_different_shop():
    v_repo = VoucherRepository()
    dedupe = DedupeService(v_repo)

    item_shop_a = {
        "platform": "SHOPEE",
        "voucher_code": "SAVE50K",
        "scope_type": "SHOP",
        "shop_id": "SHOP_A",
        "title": "Shop A 50k",
        "discount_type": "FIXED",
        "discount_value": 50000,
        "min_order_value": 0,
        "start_time": "00:00 11/10/2026",
        "end_time": "23:59 11/10/2026",
        "source_url": "https://shopee.vn/shop_a"
    }

    item_shop_b = {
        "platform": "SHOPEE",
        "voucher_code": "SAVE50K",
        "scope_type": "SHOP",
        "shop_id": "SHOP_B",
        "title": "Shop B 50k",
        "discount_type": "FIXED",
        "discount_value": 50000,
        "min_order_value": 0,
        "start_time": "00:00 11/10/2026",
        "end_time": "23:59 11/10/2026",
        "source_url": "https://shopee.vn/shop_b"
    }

    canon_a, obs_a, is_new_a, _ = dedupe.process_observation(item_shop_a, "shop_source", "SHOP_PAGE")
    canon_b, obs_b, is_new_b, _ = dedupe.process_observation(item_shop_b, "shop_source", "SHOP_PAGE")

    assert is_new_a is True
    assert is_new_b is True
    assert canon_a.id != canon_b.id
    assert canon_a.shop_id == "SHOP_A"
    assert canon_b.shop_id == "SHOP_B"


# 4. Kiểm tra gộp Canonical khi cùng voucher xuất hiện ở nhiều nguồn
def test_canonical_multi_source_merge_and_code_reveal():
    v_repo = VoucherRepository()
    dedupe = DedupeService(v_repo)

    # Lần 1: Thấy trên campaign, chưa lộ code nhập tay ("Lưu ngay")
    obs_banner = {
        "platform": "SHOPEE",
        "voucher_code": None,
        "claim_type": "SAVE_BUTTON",
        "scope_type": "PLATFORM",
        "title": "Sự kiện khung giờ vàng",
        "discount_type": "FIXED",
        "discount_value": 50000,
        "min_order_value": 0,
        "start_time": "00:00 11/10/2026",
        "end_time": "23:59 11/10/2026",
        "source_url": "https://shopee.vn/m/khung-gio-vang",
        "claim_url": "https://shopee.vn/m/khung-gio-vang"
    }
    canon1, obs1, is_new1, rev1 = dedupe.process_observation(obs_banner, "campaign_source", "CAMPAIGN_PAGE")
    assert is_new1 is True
    assert canon1.voucher_code is None
    assert rev1 is False

    # Lần 2: Nguồn cộng đồng phát hiện mã code cụ thể cho ưu đãi này
    obs_reveal = {
        "platform": "SHOPEE",
        "voucher_code": "VANG50K",
        "scope_type": "PLATFORM",
        "title": "Lộ mã VANG50K",
        "discount_type": "FIXED",
        "discount_value": 50000,
        "min_order_value": 0,
        "start_time": "00:00 11/10/2026",
        "end_time": "23:59 11/10/2026",
        "source_url": "https://shopee.vn/m/khung-gio-vang",
        "claim_url": "https://shopee.vn/m/khung-gio-vang"
    }
    canon2, obs2, is_new2, rev2 = dedupe.process_observation(obs_reveal, "community_source", "COMMUNITY_FEED")
    assert is_new2 is False
    assert rev2 is True
    assert canon2.id == canon1.id
    assert canon2.voucher_code == "VANG50K"

    # Kiểm tra bảng observations lưu đủ 2 lần
    obs_list = v_repo.get_observations(canon1.id)
    assert len(obs_list) == 2


# 5. Kiểm tra phân loại chất lượng độc lập (HIGH_RATE vs ELITE_VALUE)
def test_quality_classification_independent():
    # A. Voucher 40% nhưng trần 10k -> Đạt HIGH_RATE, KHÔNG đạt ELITE_VALUE
    v_high_rate_only = {
        "title": "Giảm 40% tối đa 10k",
        "discount_type": "PERCENT",
        "discount_value": 40,
        "max_discount": 10000,
        "min_order_value": 0,
        "is_freeship": 0
    }
    res_a = classify_voucher_quality(v_high_rate_only)
    assert res_a["is_qualified"] is True
    assert "HIGH_RATE" in res_a["tags"]
    assert "ELITE_VALUE" not in res_a["tags"]

    # B. Voucher 50k đơn 0đ -> Đạt ELITE_VALUE
    v_fixed_elite = {
        "title": "Giảm 50k đơn 0đ",
        "discount_type": "FIXED",
        "discount_value": 50000,
        "min_order_value": 0,
        "is_freeship": 0
    }
    res_b = classify_voucher_quality(v_fixed_elite)
    assert res_b["is_qualified"] is True
    assert "ELITE_VALUE" in res_b["tags"]

    # C. Voucher 35% trần 100k -> Đạt cả HIGH_RATE và ELITE_VALUE
    v_both = {
        "title": "Giảm 35% tối đa 100k",
        "discount_type": "PERCENT",
        "discount_value": 35,
        "max_discount": 100000,
        "min_order_value": 200000,
        "is_freeship": 0
    }
    res_c = classify_voucher_quality(v_both)
    assert res_c["is_qualified"] is True
    assert "HIGH_RATE" in res_c["tags"]
    assert "ELITE_VALUE" in res_c["tags"]

    # D. Freeship -> Bị loại
    v_ship = {
        "title": "Miễn phí vận chuyển toàn quốc",
        "discount_type": "FIXED",
        "discount_value": 30000,
        "min_order_value": 0,
        "is_freeship": 1
    }
    res_d = classify_voucher_quality(v_ship)
    assert res_d["is_qualified"] is False


# 6. Kiểm tra DiscoveryOrchestrator chạy đầy đủ với mock sources
def test_discovery_orchestrator_execution():
    async def _test():
        v_repo = VoucherRepository()
        s_repo = ShopRepository()
        sc_repo = ScanRepository()

        class MockHealthySource(BaseVoucherSource):
            def __init__(self):
                super().__init__("mock_healthy", "CAMPAIGN_PAGE")
            async def fetch_vouchers(self):
                return [{
                    "platform": "SHOPEE",
                    "voucher_code": "MOCK50K",
                    "title": "Mã thử nghiệm 50k",
                    "discount_type": "FIXED",
                    "discount_value": 50000,
                    "min_order_value": 0,
                    "start_time": "00:00 11/10/2026",
                    "end_time": "23:59 11/10/2026",
                    "source_url": "https://shopee.vn/mock",
                    "verification_status": "VERIFIED_ACTIVE"
                }]

        class MockNotImplementedSource(BaseVoucherSource):
            def __init__(self):
                super().__init__("mock_not_impl", "LIVE_VIDEO")
                self.status = "NOT_IMPLEMENTED"
            async def fetch_vouchers(self):
                return []

        orch = DiscoveryOrchestrator(
            voucher_repo=v_repo,
            shop_repo=s_repo,
            scan_repo=sc_repo,
            sources=[MockHealthySource(), MockNotImplementedSource()]
        )

        res = await orch.run_discovery_cycle()
        assert res["total_sources"] == 2
        assert res["raw_observations_count"] == 1
        assert res["canonical_created"] == 1
        assert len(res["events_to_notify"]) == 1
        assert res["events_to_notify"][0]["type"] == "READY_NOW"

        # Kiểm tra sức khỏe nguồn đã được lưu
        summary = v_repo.get_source_health_summary()
        assert summary["mock_healthy"]["status"] == "HEALTHY"
        assert summary["mock_not_impl"]["status"] == "NOT_IMPLEMENTED"

    asyncio.run(_test())

import pytest
from unittest.mock import AsyncMock, MagicMock
from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus, VerificationStatus
from services.lifecycle_service import LifecycleService
from services.dedupe_service import DedupeService
from core.voucher_lifecycle import evaluate_lifecycle_transition
from repositories.voucher_repository import VoucherRepository
from repositories.scan_repository import ScanRepository

def test_evaluate_lifecycle_transition_exhausted():
    v = Voucher(
        id="TEST_EXHAUSTED_1",
        platform="SHOPEE",
        title="Mã 35% Max 120k",
        scope_type=ScopeType.CATEGORY,
        discount_type=DiscountType.PERCENT,
        discount_value=35.0,
        min_order_value=0.0,
        max_discount=120000.0,
        start_time="2026-10-01 00:00",
        end_time="2026-10-31 23:59",
        source_url="https://shopee.vn",
        source_type="COMMUNITY_FEED",
        status=VoucherStatus.ACTIVE,
        percentage_used=100.0
    )
    new_status, event_name = evaluate_lifecycle_transition(v)
    assert new_status == VoucherStatus.EXHAUSTED
    assert event_name == "VOUCHER_EXHAUSTED"

def test_evaluate_lifecycle_transition_expired():
    v = Voucher(
        id="TEST_EXPIRED_1",
        platform="SHOPEE",
        title="Mã hết hạn",
        scope_type=ScopeType.CATEGORY,
        discount_type=DiscountType.FIXED,
        discount_value=50000.0,
        min_order_value=100000.0,
        start_time="2026-09-01 00:00",
        end_time="2026-09-02 23:59",
        source_url="https://shopee.vn",
        source_type="COMMUNITY_FEED",
        status=VoucherStatus.ACTIVE
    )
    new_status, event_name = evaluate_lifecycle_transition(v)
    assert new_status == VoucherStatus.EXPIRED
    assert event_name == "VOUCHER_EXPIRED"

def test_dedupe_service_stores_percentage_used(tmp_path):
    repo = VoucherRepository()
    scan_repo = ScanRepository()
    dedupe = DedupeService(repo, scan_repo)

    raw_item = {
        "voucher_code": "PCU35TEST",
        "title": "Mã Test 35%",
        "discount_type": "PERCENT",
        "discount_value": 35.0,
        "max_discount": 120000.0,
        "min_order_value": 0.0,
        "start_time": "2026-10-01 00:00",
        "end_time": "2026-10-31 23:59",
        "percentage_used": 98.0,
        "source_url": "https://shopee.vn"
    }

    canon_v, _, is_new, _ = dedupe.process_observation(raw_item, "test_src", "COMMUNITY_FEED")
    assert canon_v.percentage_used == 98.0

    # Cập nhật thành 100%
    raw_item_100 = dict(raw_item)
    raw_item_100["percentage_used"] = 100.0
    updated_v, _, is_new2, _ = dedupe.process_observation(raw_item_100, "test_src", "COMMUNITY_FEED")
    assert not is_new2
    assert updated_v.percentage_used == 100.0

@pytest.mark.anyio
async def test_telegram_broadcast_voucher_exhausted():
    from app.bot.telegram_service import TelegramBotService
    bot = TelegramBotService()
    bot.send_message = AsyncMock(return_value={"result": {"message_id": 999}})

    v = Voucher(
        id="TEST_EXHAUSTED_BROADCAST",
        platform="SHOPEE",
        voucher_code="PCU35ELHA",
        title="Mã 35% Max 120k",
        scope_type=ScopeType.CATEGORY,
        discount_type=DiscountType.PERCENT,
        discount_value=35.0,
        min_order_value=0.0,
        max_discount=120000.0,
        start_time="2026-10-01 00:00",
        end_time="2026-10-31 23:59",
        source_url="https://shopee.vn",
        source_type="COMMUNITY_FEED",
        status=VoucherStatus.EXHAUSTED,
        percentage_used=100.0
    )

    bot.voucher_repo.upsert(v)
    success = await bot.broadcast_voucher_exhausted(v, "VOUCHER_EXHAUSTED")
    assert success is True
    assert bot.send_message.called
    call_text = bot.send_message.call_args[0][0]
    assert "MÃ ĐÃ CHÁY LƯỢT DÙNG" in call_text
    assert "PCU35ELHA" in call_text

def test_lifecycle_service_notifies_exhausted_voucher():
    repo = VoucherRepository()
    scan_repo = ScanRepository()
    svc = LifecycleService(repo, scan_repo)

    v = Voucher(
        id="TEST_LIFECYCLE_EXHAUSTED",
        platform="SHOPEE",
        voucher_code="PCU35ELHA",
        title="Mã 35% Max 120k Đơn 0đ",
        scope_type=ScopeType.CATEGORY,
        discount_type=DiscountType.PERCENT,
        discount_value=35.0,
        min_order_value=0.0,
        max_discount=120000.0,
        start_time="2026-10-01 00:00",
        end_time="2026-10-31 23:59",
        source_url="https://shopee.vn",
        source_type="COMMUNITY_FEED",
        status=VoucherStatus.ACTIVE,
        percentage_used=100.0
    )
    repo.upsert(v)

    notifs = svc.run_lifecycle_cycle()
    exhausted_notifs = [n for n in notifs if n.get("type") == "VOUCHER_EXHAUSTED" and n.get("voucher").id == v.id]
    assert len(exhausted_notifs) == 1
    assert exhausted_notifs[0]["voucher"].status == VoucherStatus.EXHAUSTED

def test_get_elite_verified_vouchers_excludes_exhausted():
    repo = VoucherRepository()
    v_active = Voucher(
        id="TEST_ELITE_ACTIVE",
        platform="SHOPEE",
        voucher_code="ACTIVE123",
        title="Mã Active",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.PERCENT,
        discount_value=35.0,
        min_order_value=0.0,
        max_discount=120000.0,
        start_time="2026-10-01 00:00",
        end_time="2026-10-31 23:59",
        source_url="https://shopee.vn",
        source_type="COMMUNITY_FEED",
        verification_status=VerificationStatus.VERIFIED_ACTIVE,
        status=VoucherStatus.ACTIVE
    )
    v_exhausted = Voucher(
        id="TEST_ELITE_EXHAUSTED",
        platform="SHOPEE",
        voucher_code="EXHAUSTED123",
        title="Mã Exhausted",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.PERCENT,
        discount_value=35.0,
        min_order_value=0.0,
        max_discount=120000.0,
        start_time="2026-10-01 00:00",
        end_time="2026-10-31 23:59",
        source_url="https://shopee.vn",
        source_type="COMMUNITY_FEED",
        verification_status=VerificationStatus.VERIFIED_ACTIVE,
        status=VoucherStatus.EXHAUSTED
    )
    repo.upsert(v_active)
    repo.upsert(v_exhausted)

    verified = repo.get_elite_verified_vouchers(limit=50)
    v_ids = [v.id for v in verified]
    assert "TEST_ELITE_ACTIVE" in v_ids
    assert "TEST_ELITE_EXHAUSTED" not in v_ids


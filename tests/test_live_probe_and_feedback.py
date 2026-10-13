import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta

from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus, VerificationStatus
from repositories.voucher_repository import VoucherRepository
from services.shopee_live_checker import ShopeeLiveChecker
from app.bot.elite_keyboard import get_elite_voucher_action_keyboard
from app.bot.telegram_service import TelegramBotService

TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_live_probe.db")

@pytest.fixture(autouse=True)
def setup_test_db():
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

    repo = VoucherRepository(TEST_DB_PATH)
    repo.init_schema()

    yield repo

    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

@pytest.mark.anyio
async def test_shopee_live_checker_exhausted():
    checker = ShopeeLiveChecker()
    v = Voucher(
        id="TEST_EXHAUSTED",
        platform="SHOPEE",
        voucher_code="DEAD100K",
        title="Mã Đã Hết Lượt",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=100000,
        min_order_value=0,
        start_time="2026-10-13 12:00",
        end_time="2026-10-13 23:59",
        source_url="https://shopee.vn",
        source_type="CAMPAIGN_PAGE",
        claim_type="CODE",
        status=VoucherStatus.ACTIVE
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "error": 0,
        "data": {
            "voucher_status": 2
        }
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await checker.check_voucher_status(v)
        assert res["is_exhausted"] is True
        assert "Shopee voucher_status=2" in res["reason"]

@pytest.mark.anyio
async def test_shopee_live_checker_active():
    checker = ShopeeLiveChecker()
    v = Voucher(
        id="TEST_ACTIVE",
        platform="SHOPEE",
        voucher_code="LIVE50K",
        title="Mã Còn Lượt",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=0,
        start_time="2026-10-13 12:00",
        end_time="2026-10-13 23:59",
        source_url="https://shopee.vn",
        source_type="CAMPAIGN_PAGE",
        claim_type="CODE",
        status=VoucherStatus.ACTIVE
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "error": 0,
        "data": {
            "voucher_status": 1
        }
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        res = await checker.check_voucher_status(v)
        assert res["is_exhausted"] is False

@pytest.mark.anyio
async def test_probe_active_vouchers_updates_db(setup_test_db):
    repo = setup_test_db
    v = Voucher(
        id="CANON_PCU35_TEST",
        platform="SHOPEE",
        voucher_code="PCU35TEST",
        title="Mã Điện Tử 35%",
        scope_type=ScopeType.CATEGORY,
        discount_type=DiscountType.PERCENT,
        discount_value=35,
        max_discount=70000,
        min_order_value=0,
        start_time="2026-10-13 12:00",
        end_time="2026-10-13 23:59",
        source_url="https://shopee.vn",
        source_type="CAMPAIGN_PAGE",
        claim_type="CODE",
        status=VoucherStatus.ACTIVE
    )
    repo.upsert(v)

    checker = ShopeeLiveChecker()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "error": 2,
        "error_msg": "Voucher đã hết lượt sử dụng"
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        active_list = repo.get_active_vouchers()
        res = await checker.probe_active_vouchers(active_list, repo, delay_between_requests=0)
        assert res["exhausted_count"] == 1
        updated = repo.get_by_id("CANON_PCU35_TEST")
        assert updated.status == VoucherStatus.EXHAUSTED
        assert updated.percentage_used == 100.0

def test_upsert_auto_extract_and_exhaust_over_90(setup_test_db):
    repo = setup_test_db
    v = Voucher(
        id="CANON_EXTRACT_TEST",
        platform="SHOPEE",
        voucher_code="EXTRACT98",
        title="Mã Leak",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=0,
        start_time="2026-10-13 12:00",
        end_time="2026-10-13 23:59",
        source_url="https://shopee.vn",
        source_type="CAMPAIGN_PAGE",
        source_evidence_excerpt="Giảm 50k | Đã dùng: 98.0% | Nguồn: bloggiamgia",
        status=VoucherStatus.ACTIVE
    )
    repo.upsert(v)
    saved = repo.get_by_id("CANON_EXTRACT_TEST")
    assert saved.percentage_used == 98.0
    from core.voucher_lifecycle import evaluate_lifecycle_transition
    new_status, event = evaluate_lifecycle_transition(saved)
    assert new_status == VoucherStatus.EXHAUSTED
    assert event == "VOUCHER_EXHAUSTED"

def test_keyboard_feedback_buttons():
    markup = get_elite_voucher_action_keyboard(
        source_url="https://shopee.vn/m/sale",
        voucher_id="V_FEEDBACK_123"
    )
    rows = markup["inline_keyboard"]
    assert len(rows) == 2
    feedback_row = rows[1]
    assert feedback_row[0]["callback_data"] == "fb:like:V_FEEDBACK_123"
    assert feedback_row[1]["callback_data"] == "fb:exhaust:V_FEEDBACK_123"

@pytest.mark.anyio
async def test_callback_feedback_exhaust(setup_test_db):
    repo = setup_test_db
    v = Voucher(
        id="V_CB_TEST",
        platform="SHOPEE",
        voucher_code="CBTEST",
        title="Mã Cần Báo Hết Lượt",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=0,
        start_time="2026-10-13 12:00",
        end_time="2026-10-13 23:59",
        source_url="https://shopee.vn",
        source_type="CAMPAIGN_PAGE",
        status=VoucherStatus.ACTIVE
    )
    repo.upsert(v)

    bot = TelegramBotService()
    bot.voucher_repo = repo
    bot.send_message = AsyncMock()
    bot.answer_callback = AsyncMock()

    await bot.handle_callback_query({
        "id": "query_123",
        "data": "fb:exhaust:V_CB_TEST",
        "message": {"chat": {"id": 123456}}
    })

    updated = repo.get_by_id("V_CB_TEST")
    assert updated.status == VoucherStatus.EXHAUSTED
    assert updated.percentage_used == 100.0
    bot.send_message.assert_called_once()
    msg_args = bot.send_message.call_args[0][0]
    assert "ĐÃ GHI NHẬN HẾT LƯỢT" in msg_args

@pytest.mark.anyio
async def test_slot_aware_parsing_and_heuristic_ttl():
    from sources.community_voucher_source import CommunityVoucherSource
    source = CommunityVoucherSource()

    fake_html = '''
    <script>
    self.__next_f.push([1,"{\\"hotVouchers\\":[{\\"voucherCode\\":\\"SLOT12H50\\",\\"voucherType\\":\\"percent\\",\\"voucherAmount\\":50,\\"maxDiscount\\":100000,\\"minSpend\\":0,\\"title\\":\\"Khung 12H: Giảm 50%\\",\\"note\\":\\"Mở đợt 12H\\",\\"startAt\\":\\"2026-10-14T00:00:00Z\\",\\"expiredAt\\":\\"2026-10-31T23:59:59Z\\",\\"percentageUsed\\":10.0,\\"detailLink\\":\\"https://shopee.vn/m/12h\\"}]}"]);
    </script>
    '''

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = fake_html

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        vouchers = await source.fetch_vouchers()
        assert len(vouchers) == 1
        v = vouchers[0]
        assert v["voucher_code"] == "SLOT12H50"
        # Khung 12H phải được điều chỉnh start_time = 12:00 và end_time = 12:30 (thay vì 31/10)
        assert "12:00" in v["start_time"]
        assert "12:30" in v["end_time"]
        assert v["verification_status"] == VerificationStatus.VERIFIED_ACTIVE.value

@pytest.mark.anyio
async def test_hot_voucher_exhausted_over_90_marked_invalid():
    from sources.community_voucher_source import CommunityVoucherSource
    source = CommunityVoucherSource()

    fake_html = '''
    <script>
    self.__next_f.push([1,"{\\"hotVouchers\\":[{\\"voucherCode\\":\\"EXHAUST95\\",\\"voucherType\\":\\"percent\\",\\"voucherAmount\\":50,\\"maxDiscount\\":100000,\\"minSpend\\":0,\\"title\\":\\"Mã Đã Hết Lượt\\",\\"startAt\\":\\"2026-10-14T00:00:00Z\\",\\"expiredAt\\":\\"2026-10-31T23:59:59Z\\",\\"percentageUsed\\":95.0,\\"detailLink\\":\\"https://shopee.vn/m/sale\\"}]}"]);
    </script>
    '''

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.text = fake_html

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        vouchers = await source.fetch_vouchers()
        assert len(vouchers) == 1
        v = vouchers[0]
        # Voucher có percentageUsed >= 90% bị gắn cờ INVALID ngay tại nguồn
        assert v["verification_status"] == VerificationStatus.INVALID.value


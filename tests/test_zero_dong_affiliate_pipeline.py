import pytest
import tempfile
import os
from unittest.mock import MagicMock, AsyncMock
from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus, VerificationStatus
from core.elite_voucher_filter import is_zero_dong_affiliate_voucher, classify_voucher_quality
from sources.shopee_affiliate_campaign_source import ShopeeAffiliateCampaignSource
from repositories.voucher_repository import VoucherRepository
from repositories.shop_repository import ShopRepository
from app.bot.elite_keyboard import get_elite_main_keyboard, get_elite_voucher_action_keyboard, get_elite_back_keyboard
from app.bot.elite_templates import (
    format_zero_dong_voucher_card,
    format_zero_dong_schedule,
    format_zero_dong_scan_result
)
from app.bot.elite_commands import EliteCommands

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)

def make_test_voucher(
    id="v_test",
    title="Test Voucher",
    scope_type=ScopeType.PLATFORM,
    discount_type=DiscountType.FIXED,
    discount_value=100000.0,
    min_order_value=0.0,
    start_time="20:00 14/10",
    end_time="20:30 14/10",
    source_url="https://affiliate.shopee.vn",
    source_type="AFFILIATE_NETWORK",
    voucher_code=None,
    status=VoucherStatus.ACTIVE,
    verification_status=VerificationStatus.VERIFIED_ACTIVE,
    max_discount=None,
    is_freeship=False
) -> Voucher:
    return Voucher(
        id=id,
        title=title,
        scope_type=scope_type,
        discount_type=discount_type,
        discount_value=discount_value,
        min_order_value=min_order_value,
        start_time=start_time,
        end_time=end_time,
        source_url=source_url,
        source_type=source_type,
        voucher_code=voucher_code,
        status=status,
        verification_status=verification_status,
        max_discount=max_discount,
        is_freeship=is_freeship
    )

def test_is_zero_dong_affiliate_voucher_filter():
    # 1. Đơn 0đ + Giảm cố định >= 30k -> HỢP LỆ
    v_valid_fixed = make_test_voucher(
        id="v_aff_100k",
        voucher_code="AFF100KTOANSAN",
        discount_type=DiscountType.FIXED,
        discount_value=100000,
        min_order_value=0
    )
    assert is_zero_dong_affiliate_voucher(v_valid_fixed) is True
    assert "ZERO_DONG_AFFILIATE" in classify_voucher_quality(v_valid_fixed)["tags"]

    # 2. Đơn > 0đ (ví dụ 99k, 400k) -> BỊ LOẠI
    v_min_spend = make_test_voucher(
        id="v_aff_min99k",
        voucher_code="AFF99K",
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=99000
    )
    assert is_zero_dong_affiliate_voucher(v_min_spend) is False

    # 3. Mã Freeship -> BỊ LOẠI 100%
    v_freeship = make_test_voucher(
        id="v_fs",
        voucher_code="FREESHIP0D",
        discount_type=DiscountType.FIXED,
        discount_value=30000,
        min_order_value=0,
        is_freeship=True
    )
    assert is_zero_dong_affiliate_voucher(v_freeship) is False

    # 4. Giảm % >= 30% và trần >= 30k -> HỢP LỆ
    v_percent_good = make_test_voucher(
        id="v_pct_ok",
        voucher_code="KOL35PCT",
        discount_type=DiscountType.PERCENT,
        discount_value=35,
        max_discount=120000,
        min_order_value=0
    )
    assert is_zero_dong_affiliate_voucher(v_percent_good) is True

    # 5. Giảm % nhưng trần < 30k (ví dụ 50% tối đa 15k) -> BỊ LOẠI
    v_percent_low_cap = make_test_voucher(
        id="v_pct_bad",
        voucher_code="KOL50PCT15K",
        discount_type=DiscountType.PERCENT,
        discount_value=50,
        max_discount=15000,
        min_order_value=0
    )
    assert is_zero_dong_affiliate_voucher(v_percent_low_cap) is False

    # 6. Giảm cố định < 30k (ví dụ 10k, 20k) -> BỊ LOẠI
    v_fixed_low = make_test_voucher(
        id="v_fixed_low",
        voucher_code="AFF20K",
        discount_type=DiscountType.FIXED,
        discount_value=20000,
        min_order_value=0
    )
    assert is_zero_dong_affiliate_voucher(v_fixed_low) is False

    # 7. Mã nội suy giả lập (AFF18H1410, ELITE100K) -> BỊ CHẶN TUYỆT ĐỐI
    v_synthetic = make_test_voucher(
        id="v_fake",
        voucher_code="AFF18H1410",
        discount_type=DiscountType.FIXED,
        discount_value=100000,
        min_order_value=0
    )
    assert is_zero_dong_affiliate_voucher(v_synthetic) is False

@pytest.mark.anyio
async def test_shopee_affiliate_campaign_source_never_returns_synthetic_vouchers():
    source = ShopeeAffiliateCampaignSource()
    vouchers = await source.fetch_vouchers()

    import re
    for v in vouchers:
        # Tuyệt đối không chứa mã nội suy công thức
        code = str(v.get("voucher_code") or "")
        assert not re.match(r"^AFF\d{1,2}H\d{4}$", code)
        assert v["min_order_value"] <= 0
        assert not v.get("is_freeship", False)
        assert v["source_type"] == "AFFILIATE_NETWORK"

def test_minimalist_3_button_keyboard_layout():
    kb = get_elite_main_keyboard()
    rows = kb["inline_keyboard"]
    assert len(rows) == 2
    # Hàng 1: [ 🔥 Mã Đơn 0Đ Đang Mở ]   [ ⏳ Lịch Săn Khung Giờ ]
    assert len(rows[0]) == 2
    assert rows[0][0]["callback_data"] == "action:zero_dong_active"
    assert rows[0][1]["callback_data"] == "action:zero_dong_upcoming"
    # Hàng 2: [ 🔍 Quét Ngay ]
    assert len(rows[1]) == 1
    assert rows[1][0]["callback_data"] == "action:zero_dong_scan"

def test_zero_dong_templates():
    # 1. format_zero_dong_voucher_card cho mã nhập tay
    v_code = make_test_voucher(
        id="v_c",
        voucher_code="AFF100KTOANSAN",
        discount_type=DiscountType.FIXED,
        discount_value=100000,
        min_order_value=0,
        start_time="20:00 14/10",
        end_time="20:30 14/10"
    )
    card_txt, card_markup = format_zero_dong_voucher_card(v_code)
    assert "Giảm 100.000đ (Đơn 0đ)" in card_txt
    assert "AFF100KTOANSAN" in card_txt
    assert "20:00 14/10 — 20:30 14/10" in card_txt
    assert card_markup is None  # Code nhập tay -> copy 1 chạm, không nút rườm rà

    # 2. format_zero_dong_voucher_card cho mã lưu banner
    v_banner = make_test_voucher(
        id="v_b",
        voucher_code=None,
        title="Mã Lưu Banner 50k",
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=0,
        start_time="20:00 14/10",
        end_time="20:30 14/10",
        source_url="https://shopee.vn/m/khung-gio-vang"
    )
    banner_txt, banner_markup = format_zero_dong_voucher_card(v_banner)
    assert "Giảm 50.000đ (Đơn 0đ)" in banner_txt
    assert banner_markup is not None
    assert banner_markup["inline_keyboard"][0][0]["text"] == "Lưu mã #1 (50.000đ)"
    assert banner_markup["inline_keyboard"][0][0]["url"] == "https://shopee.vn/m/khung-gio-vang"

    # 3. format_zero_dong_schedule
    sched_txt = format_zero_dong_schedule([v_code, v_banner])
    assert "LỊCH MỞ MÃ ĐƠN 0Đ TIẾP THEO" in sched_txt
    assert "Khung 20:00" in sched_txt

    # 4. format_zero_dong_scan_result
    scan_txt = format_zero_dong_scan_result([v_code])
    assert "KẾT QUẢ QUÉT SHOPEE RADAR" in scan_txt
    assert "Tìm thấy 1 mã đơn 0đ mới" in scan_txt
    assert "AFF100KTOANSAN" in scan_txt

@pytest.mark.anyio
async def test_elite_commands_zero_dong_flow(temp_db):
    repo = VoucherRepository(db_path=temp_db)
    shop_repo = ShopRepository(db_path=temp_db)
    disc_mock = MagicMock()

    # Nạp voucher 0đ active
    v_active = make_test_voucher(
        id="v_act",
        voucher_code="AFF200K0D",
        title="Mã Tiếp Thị 200k Đơn 0đ",
        discount_type=DiscountType.FIXED,
        discount_value=200000,
        min_order_value=0,
        start_time="2026-10-14 20:00:00",
        end_time="2026-10-14 20:30:00",
        status=VoucherStatus.ACTIVE,
        verification_status=VerificationStatus.VERIFIED_ACTIVE
    )
    repo.upsert(v_active)

    # Nạp voucher 0đ upcoming
    v_up = make_test_voucher(
        id="v_up",
        voucher_code="AFF500K0D",
        title="Mã Tiếp Thị 500k Đơn 0đ",
        discount_type=DiscountType.FIXED,
        discount_value=500000,
        min_order_value=0,
        start_time="2026-10-15 00:00:00",
        end_time="2026-10-15 00:30:00",
        status=VoucherStatus.UPCOMING_CODE_KNOWN,
        verification_status=VerificationStatus.VERIFIED_UPCOMING
    )
    repo.upsert(v_up)

    commands = EliteCommands(repo, shop_repo, disc_mock)

    # 1. Bấm nút 🔥 Mã Đơn 0Đ Đang Mở
    msg_active, kb_active = await commands.handle_zero_dong_active()
    assert "AFF200K0D" in msg_active
    assert "Giảm 200.000đ (Đơn 0đ)" in msg_active
    assert "Menu chính" in str(kb_active)

    # 2. Bấm nút ⏳ Lịch Săn Khung Giờ
    msg_up, kb_up = await commands.handle_zero_dong_upcoming()
    assert "LỊCH MỞ MÃ ĐƠN 0Đ TIẾP THEO" in msg_up
    assert "AFF500K0D" in msg_up
    assert "500.000đ" in msg_up

    # 3. Bấm nút 🔍 Quét Ngay
    orchestrator_mock = MagicMock()
    orchestrator_mock.run_discovery_cycle = AsyncMock(return_value={"total_sources": 5})
    commands.orchestrator = orchestrator_mock

    msg_scan, kb_scan = await commands.handle_zero_dong_scan()
    assert "KẾT QUẢ QUÉT SHOPEE RADAR" in msg_scan
    assert "AFF200K0D" in msg_scan
    orchestrator_mock.run_discovery_cycle.assert_awaited_once()

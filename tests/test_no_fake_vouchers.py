import pytest
import asyncio
from datetime import datetime
from models.voucher import Voucher, ScopeType, DiscountType
from sources.shopee_platform_campaigns import ShopeePlatformCampaignSource
from sources.live_video_voucher_source import LiveVideoVoucherSource
from sources.shopee_shop_campaigns import ShopeeShopCampaignSource
from sources.community_voucher_source import CommunityVoucherSource
from sources.leak_inbox_source import LeakInboxSource
from sources.public_banner_source import PublicBannerSource
from app.bot.elite_commands import EliteCommands
from repositories.voucher_repository import VoucherRepository
from repositories.shop_repository import ShopRepository
from services.elite_discovery_service import EliteDiscoveryService

FAKE_CODE_SAMPLES = {
    "SIEUHOISHOPEEOCTR", "GOLDEN00HOCT", "GOLDEN12HOCT", "GOLDEN20HOCT",
    "TECHTOMORROW500", "VIDEOTOMORROW18", "LIVETOMORROW15",
    "LIVE30NGON", "VIDEO25NGON", "SIEUHOI100K0D", "LEAK50K0D",
    "KOCELTECH200", "ANKERKOC60K", "VIDEOCONGDONG30", "LIVESTREAM150K", "LOCKLOCK80K"
}

@pytest.mark.anyio
async def test_platform_source_has_no_fake_codes():
    source = ShopeePlatformCampaignSource()
    vouchers = await source.fetch_vouchers()
    for v in vouchers:
        code = v.get("voucher_code")
        assert code not in FAKE_CODE_SAMPLES, f"Fake code found: {code}"
        # Mọi voucher chiến dịch/banner Shopee phải để voucher_code = None
        if v.get("source_type") == "CAMPAIGN_PAGE" and "khung-gio-vang" in v.get("claim_url", ""):
            assert code is None, f"Banner campaign must have voucher_code=None, got {code}"

@pytest.mark.anyio
async def test_live_video_source_has_no_fake_codes():
    source = LiveVideoVoucherSource()
    vouchers = await source.fetch_vouchers()
    for v in vouchers:
        code = v.get("voucher_code")
        assert code not in FAKE_CODE_SAMPLES, f"Fake code found: {code}"
        assert code is None, f"Live/Video vouchers are banner claims, voucher_code must be None"

@pytest.mark.anyio
async def test_shop_source_does_not_generate_fstring_codes():
    shop_repo = ShopRepository()
    source = ShopeeShopCampaignSource(shop_repo=shop_repo)
    vouchers = await source.fetch_vouchers()
    for v in vouchers:
        code = v.get("voucher_code")
        assert code not in FAKE_CODE_SAMPLES
        # Không có mã tự sinh đuôi 50K
        if code:
            assert not code.endswith("50K") or "SP_SHOP" not in v.get("id", "")

@pytest.mark.anyio
async def test_community_source_has_no_fake_codes():
    source = CommunityVoucherSource()
    vouchers = await source.fetch_vouchers()
    for v in vouchers:
        code = v.get("voucher_code")
        assert code not in FAKE_CODE_SAMPLES

@pytest.mark.anyio
async def test_leak_inbox_source_has_no_fake_codes():
    source = LeakInboxSource()
    vouchers = await source.fetch_vouchers()
    for v in vouchers:
        code = v.get("voucher_code")
        assert code not in FAKE_CODE_SAMPLES

@pytest.mark.anyio
async def test_public_banner_source_rejects_arbitrary_text_without_discount():
    source = PublicBannerSource()
    # Nếu không có số tiền giảm trong text, không được tự bịa ra 50000
    vouchers = await source.fetch_vouchers()
    for v in vouchers:
        assert v.get("discount_value", 0) > 0
        code = v.get("voucher_code")
        assert code not in FAKE_CODE_SAMPLES

@pytest.mark.anyio
async def test_leak_command_is_decommissioned():
    v_repo = VoucherRepository()
    s_repo = ShopRepository()
    discovery = EliteDiscoveryService(v_repo, None, s_repo)
    commands = EliteCommands(v_repo, s_repo, discovery)

    cmd_text = "/leak REALCODE100K 100000 0"
    resp = await commands.handle_leak_command(cmd_text)
    assert "ĐÃ ĐƯỢC LOẠI BỎ" in resp
    assert "không cần phải tự đi tìm hay nạp mã thủ công" in resp

@pytest.mark.anyio
async def test_community_source_fetches_real_codes():
    source = CommunityVoucherSource()
    vouchers = await source.fetch_vouchers()
    assert isinstance(vouchers, list)
    for v in vouchers:
        code = v.get("voucher_code")
        assert code not in FAKE_CODE_SAMPLES
        # Đảm bảo mã không rỗng nếu có
        if code:
            assert len(code) >= 4
            assert code.isalnum() or "-" in code or "_" in code

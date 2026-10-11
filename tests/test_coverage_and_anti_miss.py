import pytest
import os
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from sources.shopee_shop_campaigns import ShopeeShopCampaignSource
from sources.shopee_platform_campaigns import ShopeePlatformCampaignSource
from services.elite_discovery_service import EliteDiscoveryService
from models.tracked_shop import TrackedShop
from repositories.shop_repository import ShopRepository
from repositories.voucher_repository import VoucherRepository
from repositories.scan_repository import ScanRepository
from app.bot.elite_commands import EliteCommands
from models.voucher import VerificationStatus, ScopeType

VN_TZ = timezone(timedelta(hours=7))

# 1. Kiểm tra ShopeeShopCampaignSource nhận diện SHOPEE_COOKIE từ môi trường
def test_1_shop_crawler_cookie_detection():
    with patch.dict(os.environ, {"SHOPEE_COOKIE": "SPC_EC=dummy_test_cookie; SPC_U=12345"}):
        source = ShopeeShopCampaignSource()
        assert source.get_shopee_cookie() == "SPC_EC=dummy_test_cookie; SPC_U=12345"

# 2. Kiểm tra ShopeeShopCampaignSource hoạt động bình thường khi không có cookie
def test_2_shop_crawler_fallback_no_cookie():
    with patch.dict(os.environ, {}, clear=True):
        source = ShopeeShopCampaignSource()
        assert source.get_shopee_cookie() is None

# 3. Kiểm tra parse API voucher của Shop thành model VERIFIED_ACTIVE
def test_3_shop_crawler_parses_shopee_api_response():
    async def _test():
        source = ShopeeShopCampaignSource()
        shop = TrackedShop(
            shop_id="26569109",
            shop_name="Anker Official Store",
            shop_url="https://shopee.vn/anker_official",
            enabled=1
        )

        mock_api_payload = {
            "data": {
                "vouchers": [
                    {
                        "voucher_code": "ANKER50K",
                        "discount_value": 50000,
                        "discount_percentage": 0,
                        "min_spend": 150000,
                        "start_time": int(datetime.now(timezone.utc).timestamp()) - 3600,
                        "end_time": int(datetime.now(timezone.utc).timestamp()) + 86400,
                        "description": "Voucher Anker giảm 50k"
                    }
                ]
            }
        }

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_api_payload

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp

        with patch.dict(os.environ, {"SHOPEE_COOKIE": "SPC_EC=valid_cookie"}):
            vouchers = await source._fetch_shop_api(mock_client, shop)
            assert len(vouchers) == 1
            v = vouchers[0]
            assert v["voucher_code"] == "ANKER50K"
            assert v["discount_value"] == 50000
            assert v["min_order_value"] == 150000
            assert v["scope_type"] == "SHOP"
            assert v["verification_status"] == VerificationStatus.VERIFIED_ACTIVE.value
            assert "Anker Official Store" in v["title"]
            assert v["source_url"] == "https://shopee.vn/Anker Official Store"
            assert v["is_freeship"] == 0
    asyncio.run(_test())

# 4. Kiểm tra ShopeePlatformCampaignSource đính kèm Cookie vào header
def test_4_shopee_platform_injects_cookie():
    async def _test():
        source = ShopeePlatformCampaignSource()
        with patch.dict(os.environ, {"SHOPEE_COOKIE": "SPC_EC=platform_cookie_test"}):
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_resp = MagicMock()
                mock_resp.status_code = 200
                mock_resp.text = "<html><body>Shopee Campaign</body></html>"
                mock_get.return_value = mock_resp

                await source._fetch_public_page_vouchers("https://shopee.vn/m/ma-giam-gia")
                called_headers = mock_get.call_args[1]["headers"]
                assert "Cookie" in called_headers
                assert called_headers["Cookie"] == "SPC_EC=platform_cookie_test"
    asyncio.run(_test())

# 5. Kiểm tra kết quả lệnh /coverage trên Telegram
def test_5_coverage_command_output():
    async def _test():
        voucher_repo = VoucherRepository()
        shop_repo = ShopRepository()
        discovery_service = EliteDiscoveryService(voucher_repo, scan_repo=None, shop_repo=shop_repo)
        commands = EliteCommands(voucher_repo, shop_repo, discovery_service)

        with patch.dict(os.environ, {"SHOPEE_COOKIE": "SPC_EC=dummy"}):
            msg = await commands.handle_coverage_command()
            assert "BÁO CÁO ĐỘ BAO PHỦ DỮ LIỆU" in msg
            assert "ĐÃ KẾT NỐI" in msg
            assert "Akamai 403" in msg

        with patch.dict(os.environ, {}, clear=True):
            msg_no_cookie = await commands.handle_coverage_command()
            assert "BÁO CÁO ĐỘ BAO PHỦ DỮ LIỆU" in msg_no_cookie
            assert "CHƯA CẤU HÌNH" in msg_no_cookie
    asyncio.run(_test())

# 6. Kiểm tra run_elite_scan trả về metadata coverage
def test_6_discovery_scan_returns_coverage_metadata():
    async def _test():
        discovery = EliteDiscoveryService()
        async def mock_empty():
            return []

        discovery.platform_source.fetch_vouchers = mock_empty
        discovery.shop_source.fetch_vouchers = mock_empty
        discovery.personal_source.fetch_vouchers = mock_empty
        discovery.banner_source.fetch_vouchers = mock_empty
        discovery.community_source.fetch_vouchers = mock_empty
        discovery.payment_source.fetch_vouchers = mock_empty
        discovery.live_video_source.fetch_vouchers = mock_empty
        discovery.leak_source.fetch_vouchers = mock_empty

        res = await discovery.run_elite_scan()
        assert "coverage_stats" in res
        assert "cookie_active" in res
        assert "sources_scanned" in res["coverage_stats"]
    asyncio.run(_test())

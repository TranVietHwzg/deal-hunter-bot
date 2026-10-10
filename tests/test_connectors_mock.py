import pytest
import asyncio
from app.connectors.shopee_connector import ShopeeConnector
from app.connectors.lazada_connector import LazadaConnector
from app.connectors.tiktok_connector import TikTokConnector
from config.feature_flags import feature_flags
from app.core.junk_filter import validate_voucher

def test_mock_three_platforms_ingestion():
    # 1. Shopee (Enabled)
    shopee = ShopeeConnector()
    vouchers = asyncio.run(shopee.fetch_vouchers())
    assert len(vouchers) > 0
    # Đảm bảo 100% không có voucher freeship
    for v in vouchers:
        assert "ship" not in v["title"].lower()
        assert v.get("is_freeship", 0) == 0

    # 2. Lazada (Disabled via feature flag)
    lazada = LazadaConnector()
    lz_vouchers = asyncio.run(lazada.fetch_vouchers())
    assert len(lz_vouchers) == 0 # Trả về mảng rỗng an toàn khi feature flag tắt

    # 3. TikTok (Disabled via feature flag)
    tiktok = TikTokConnector()
    tt_vouchers = asyncio.run(tiktok.fetch_vouchers())
    assert len(tt_vouchers) == 0

def test_connector_fault_injection_and_circuit_breaker():
    shopee = ShopeeConnector()
    # Giả lập 5 lỗi liên tiếp (HTTP 429 / 503)
    for _ in range(5):
        shopee.circuit_breaker.record_failure()

    # Circuit breaker phải ngắt ngay sang OPEN
    assert shopee.circuit_breaker.state == "OPEN"
    assert shopee.circuit_breaker.can_execute() is False

def test_invalid_corrupted_voucher_payload():
    # Payload thiếu dữ liệu, sai format hoặc discount âm
    bad_payloads = [
        {"voucher_type": "PLATFORM", "discount_value": -50000},
        {"voucher_type": "SHOP", "title": "Mã rác", "discount_value": 0},
        {"voucher_type": "FREESHIP", "title": "Free ship", "discount_value": 30000}
    ]
    for p in bad_payloads:
        is_valid, _ = validate_voucher(p)
        assert is_valid is False

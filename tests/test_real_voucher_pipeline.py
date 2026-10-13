import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from models.voucher import Voucher, ScopeType, DiscountType, VerificationStatus, VoucherStatus
from core.elite_voucher_filter import is_elite_voucher
from core.elite_score_calculator import calculate_elite_score
from sources.telegram_channel_source import TelegramChannelSource
from sources.community_voucher_source import CommunityVoucherSource
from sources.personal_eligible_voucher_source import PersonalEligibleVoucherSource
from sources.shopee_platform_campaigns import ShopeePlatformCampaignSource
from repositories.voucher_repository import VoucherRepository

VN_TZ = timezone(timedelta(hours=7))

# 1. TelegramChannelSource parse tin nhắn có mã nhập tay
def test_telegram_channel_source_parses_manual_code():
    source = TelegramChannelSource()
    raw_html = (
        '<div class="tgme_widget_message_text" dir="auto">'
        '🔥 Nhập mã <code>SALE50K0D</code> giảm 50k đơn từ 0đ toàn sàn lúc 12h!<br>'
        'Link áp mã: <a href="https://s.shopee.vn/abc123xyz">https://s.shopee.vn/abc123xyz</a>'
        '</div>'
    )
    item = source._parse_message(raw_html, "magiamgiashopee")
    assert item is not None
    assert item["voucher_code"] == "SALE50K0D"
    assert item["discount_value"] == 50000.0
    assert item["min_order_value"] == 0.0
    assert item["verification_status"] == VerificationStatus.COMMUNITY_LEAK.value
    assert item["claim_type"] == "CODE"
    assert "12:00" in item["start_time"]
    assert "https://s.shopee.vn/abc123xyz" in item["source_url"]

# 2. TelegramChannelSource parse tin nhắn bấm lưu trực tiếp (SAVE_BUTTON)
def test_telegram_channel_source_parses_save_button_deal():
    source = TelegramChannelSource()
    raw_html = (
        '<div class="tgme_widget_message_text" dir="auto">'
        '🔥 Back toàn sàn 80k/0đ, 30% lúc 20h: <a href="https://s.shopee.vn/5VVnjKONw8">https://s.shopee.vn/5VVnjKONw8</a>'
        '</div>'
    )
    item = source._parse_message(raw_html, "magiamgiashopee")
    assert item is not None
    assert item["voucher_code"] is None
    assert item["claim_type"] == "SAVE_BUTTON"
    assert item["discount_value"] in (80000.0, 30.0)
    assert item["min_order_value"] == 0.0
    assert item["verification_status"] == VerificationStatus.COMMUNITY_LEAK.value
    assert "https://s.shopee.vn/5VVnjKONw8" in item["source_url"]

# 3. TelegramChannelSource loại bỏ freeship
def test_telegram_channel_source_rejects_freeship():
    source = TelegramChannelSource()
    raw_html = (
        '<div class="tgme_widget_message_text" dir="auto">'
        'Mã freeship 0đ toàn sàn đơn 0đ: <a href="https://shopee.vn/m/freeship">Lưu ngay</a>'
        '</div>'
    )
    item = source._parse_message(raw_html, "magiamgiashopee")
    assert item is None

# 4. is_elite_voucher chấp nhận mã COMMUNITY_LEAK có code đạt chuẩn
def test_elite_filter_accepts_community_leak_code():
    now = datetime.now(VN_TZ)
    today = now.strftime("%d/%m/%Y")
    leak_voucher = {
        "voucher_code": "LEAK30K",
        "verification_status": VerificationStatus.COMMUNITY_LEAK.value,
        "discount_type": "FIXED",
        "discount_value": 30000.0,
        "min_order_value": 0.0,
        "source_url": "https://t.me/s/magiamgiashopee",
        "start_time": f"00:00 {today}",
        "end_time": f"23:59 {today}",
        "title": "Mã leak 30k đơn 0đ",
        "is_freeship": 0
    }
    is_elite, reason = is_elite_voucher(leak_voucher, require_evidence=True)
    assert is_elite is True
    assert "Đạt Elite" in reason

# 5. is_elite_voucher chấp nhận mã SAVE_BUTTON có direct URL đạt chuẩn
def test_elite_filter_accepts_community_leak_save_button():
    now = datetime.now(VN_TZ)
    today = now.strftime("%d/%m/%Y")
    leak_voucher = {
        "voucher_code": None,
        "claim_type": "SAVE_BUTTON",
        "verification_status": VerificationStatus.COMMUNITY_LEAK.value,
        "discount_type": "FIXED",
        "discount_value": 50000.0,
        "min_order_value": 0.0,
        "source_url": "https://s.shopee.vn/save50k",
        "start_time": f"00:00 {today}",
        "end_time": f"23:59 {today}",
        "title": "Mã lưu ví 50k đơn 0đ",
        "is_freeship": 0
    }
    is_elite, reason = is_elite_voucher(leak_voucher, require_evidence=True)
    assert is_elite is True
    assert "Đạt Elite" in reason

# 6. ShopeePlatformCampaignSource không sinh mock catalog events
@pytest.mark.anyio
async def test_platform_campaign_source_no_mock_catalog():
    source = ShopeePlatformCampaignSource()
    vouchers = await source.fetch_vouchers()
    for v in vouchers:
        v_id = v.get("id", "")
        assert not v_id.startswith("SP_GOLDEN_"), f"Mock item found: {v_id}"
        assert not v_id.startswith("SP_CAMP_"), f"Mock item found: {v_id}"
        assert v.get("category") != "Khung Giờ Vàng 00H"

# 7. PersonalEligibleVoucherSource tôn trọng SHOPEE_COOKIE
def test_personal_eligible_voucher_source_cookie_awareness(monkeypatch):
    monkeypatch.delenv("SHOPEE_COOKIE", raising=False)
    source_no_cookie = PersonalEligibleVoucherSource()
    assert source_no_cookie.is_connected is False
    assert "Chưa kết nối" in source_no_cookie.get_status_message()

    monkeypatch.setenv("SHOPEE_COOKIE", "SPC_EC=dummy_test_cookie")
    source_with_cookie = PersonalEligibleVoucherSource()
    assert source_with_cookie.is_connected is True
    assert "Đã kết nối" in source_with_cookie.get_status_message()

# 8. Repository get_elite_verified_vouchers bao gồm cả COMMUNITY_LEAK
def test_voucher_repository_queries_community_leak():
    repo = VoucherRepository()
    now = datetime.now(VN_TZ)
    today = now.strftime("%d/%m/%Y")
    v = Voucher(
        id="TEST_LEAK_QUERY_1",
        platform="SHOPEE",
        voucher_code="LEAKQUERY1",
        title="Test Leak Query",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000.0,
        min_order_value=0.0,
        start_time=f"00:00 {today}",
        end_time=f"23:59 {today}",
        status=VoucherStatus.ACTIVE,
        verification_status=VerificationStatus.COMMUNITY_LEAK,
        source_url="https://t.me/s/test",
        source_type="TELEGRAM_COMMUNITY"
    )
    repo.upsert(v)

    elites = repo.get_elite_verified_vouchers(limit=100)
    found = any(item.id == "TEST_LEAK_QUERY_1" for item in elites)
    assert found is True

    leaks = repo.get_community_leak_vouchers(limit=100)
    found_leak = any(item.id == "TEST_LEAK_QUERY_1" for item in leaks)
    assert found_leak is True

    # Cleanup test record
    with repo.transaction() as cur:
        cur.execute("DELETE FROM vouchers WHERE id = 'TEST_LEAK_QUERY_1'")

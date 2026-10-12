import pytest
import sqlite3
import tempfile
import os
from unittest.mock import AsyncMock, patch, MagicMock
from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus, VerificationStatus
from app.bot.elite_templates import (
    format_code_block,
    format_elite_shop_voucher,
    format_elite_upcoming_known,
    format_elite_code_revealed
)
from app.bot.notification_templates import (
    format_upcoming_known_code,
    format_active_voucher,
    format_countdown_reminder,
    format_code_revealed
)
from app.bot.elite_keyboard import get_elite_voucher_action_keyboard
from app.bot.elite_commands import EliteCommands
from app.bot.telegram_service import TelegramBotService
from repositories.voucher_repository import VoucherRepository
from repositories.shop_repository import ShopRepository
from services.elite_discovery_service import EliteDiscoveryService
from services.lifecycle_service import LifecycleService

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)

def make_voucher(
    id="v1",
    voucher_code=None,
    discount_type=DiscountType.FIXED,
    discount_value=30000.0,
    min_order_value=0.0,
    max_discount=None,
    status=VoucherStatus.ACTIVE,
    verification_status=VerificationStatus.VERIFIED_ACTIVE,
    start_time="2026-10-15 00:00:00",
    end_time="2026-10-15 23:59:59",
    scope_type=ScopeType.PLATFORM,
    shop_url=None,
    source_url="https://shopee.vn",
    source_type="BANNER",
    claim_type="CODE",
    confidence_score=90
):
    return Voucher(
        id=id,
        title="Test Voucher",
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
        shop_url=shop_url,
        max_discount=max_discount,
        claim_type=claim_type,
        confidence_score=confidence_score
    )

def test_format_code_block_never_renders_none():
    # 1. Voucher có code hợp lệ
    v_code = make_voucher(id="v1", voucher_code="ELITE30K")
    res_code = format_code_block(v_code)
    assert "ELITE30K" in res_code
    assert "None" not in res_code
    assert "Chạm để sao chép" in res_code

    # 2. Voucher voucher_code là None hoặc chuỗi "None"
    v_none = make_voucher(
        id="v2", voucher_code=None,
        claim_type="SAVE_BUTTON", shop_url="https://shopee.vn/shop/123"
    )
    res_none = format_code_block(v_none)
    assert "None" not in res_none
    assert "BẤM LƯU TẠI SHOP / BANNER" in res_none
    assert "https://shopee.vn/shop/123" in res_none

    # 3. Voucher sắp mở chưa lộ code
    v_up = make_voucher(
        id="v3", voucher_code="None",
        start_time="2026-10-15 00:00:00",
        status=VoucherStatus.UPCOMING_UNKNOWN_CODE,
        verification_status=VerificationStatus.UPCOMING_UNKNOWN_CODE
    )
    res_up = format_code_block(v_up)
    assert "None" not in res_up
    assert "ĐỢI LỘ MÃ (2026-10-15 00:00:00)" in res_up

    # 4. Voucher hết lượt
    v_exh = make_voucher(
        id="v4", voucher_code=None,
        status=VoucherStatus.EXHAUSTED,
        verification_status=VerificationStatus.UNVERIFIED
    )
    res_exh = format_code_block(v_exh)
    assert "None" not in res_exh
    assert "Tạm hết lượt lưu" in res_exh

def test_notification_templates_no_none_rendered():
    v = make_voucher(
        id="v_test", voucher_code=None,
        claim_type="SAVE_BUTTON", shop_url="https://shopee.vn/mall",
        source_url="https://shopee.vn/campaign",
        discount_value=50000, min_order_value=150000,
        start_time="2026-10-15 12:00:00", end_time="2026-10-15 23:59:59"
    )

    t_active = format_active_voucher(v)
    assert "None" not in t_active
    assert "BẤM LƯU TẠI SHOP / BANNER" in t_active

    t_reminder = format_countdown_reminder(v, "REMINDER_15M")
    assert "None" not in t_reminder

    t_known = format_upcoming_known_code(v)
    assert "None" not in t_known

    t_revealed = format_code_revealed(v)
    assert "None" not in t_revealed

def test_elite_voucher_action_keyboard_always_has_two_buttons():
    # Trường hợp 1: Có shop_url
    kb1 = get_elite_voucher_action_keyboard(
        source_url="https://shopee.vn/campaign",
        shop_url="https://shopee.vn/official-store"
    )
    buttons1 = kb1["inline_keyboard"][0]
    assert len(buttons1) == 2
    assert buttons1[0]["text"] == "🏪 Mở shop / Lưu"
    assert buttons1[0]["url"] == "https://shopee.vn/official-store"
    assert buttons1[1]["text"] == "🌐 Mở nguồn"
    assert buttons1[1]["url"] == "https://shopee.vn/campaign"

    # Trường hợp 2: Không có shop_url -> fallback source_url
    kb2 = get_elite_voucher_action_keyboard(
        source_url="https://shopee.vn/sieusale",
        shop_url=None
    )
    buttons2 = kb2["inline_keyboard"][0]
    assert len(buttons2) == 2
    assert buttons2[0]["text"] == "🏪 Mở shop / Lưu"
    assert buttons2[0]["url"] == "https://shopee.vn/sieusale"
    assert buttons2[1]["text"] == "🌐 Mở nguồn"
    assert buttons2[1]["url"] == "https://shopee.vn/sieusale"

@pytest.mark.anyio
async def test_handle_super_vouchers_includes_70_and_80_scores(temp_db):
    repo = VoucherRepository(db_path=temp_db)
    shop_repo = ShopRepository(db_path=temp_db)
    disc_service = MagicMock(spec=EliteDiscoveryService)

    # Thêm 1 voucher >= 80 điểm (100k/0đ platform)
    v_super = make_voucher(
        id="v_super_1", voucher_code="SUPER100",
        discount_value=100000, min_order_value=0,
        scope_type=ScopeType.PLATFORM, confidence_score=95
    )
    repo.upsert(v_super)

    # Thêm 1 voucher 70-79 điểm (30k/0đ platform)
    v_worthy = make_voucher(
        id="v_worthy_1", voucher_code="WORTHY30",
        discount_value=30000, min_order_value=0,
        scope_type=ScopeType.PLATFORM, confidence_score=90
    )
    repo.upsert(v_worthy)

    commands = EliteCommands(repo, shop_repo, disc_service)
    msg, kb = await commands.handle_super_vouchers()

    assert ">= 70 ĐIỂM" in msg
    assert "SIÊU XỊN" in msg
    assert "ĐÁNG LẤY" in msg
    assert "SUPER100" in msg
    assert "WORTHY30" in msg

def test_cleanup_old_records_prunes_db(temp_db):
    repo = VoucherRepository(db_path=temp_db)

    with repo.transaction() as cur:
        # Thêm voucher hết hạn hơn 8 ngày trước
        cur.execute("""
        INSERT INTO vouchers (id, platform, voucher_code, status, updated_at, end_time)
        VALUES ('v_old', 'SHOPEE', 'OLDCODE', 'EXPIRED', datetime('now', '-9 days'), datetime('now', '-9 days'));
        """)
        # Thêm voucher ACTIVE còn mới
        cur.execute("""
        INSERT INTO vouchers (id, platform, voucher_code, status, updated_at, end_time)
        VALUES ('v_fresh', 'SHOPEE', 'FRESHCODE', 'ACTIVE', datetime('now'), datetime('now', '+2 days'));
        """)

    # Chạy cleanup
    res = repo.cleanup_old_records()
    assert res["expired_vouchers"] >= 1

    # Kiểm tra voucher cũ đã bị xóa, voucher mới vẫn còn
    assert repo.get_by_id("v_old") is None
    assert repo.get_by_id("v_fresh") is not None

def test_telegram_bot_service_reuses_http_client():
    bot = TelegramBotService(token="123456:FAKE_TOKEN", chat_id="999999")
    c1 = bot.get_http_client()
    c2 = bot.get_http_client()
    assert c1 is c2
    assert not c1.is_closed

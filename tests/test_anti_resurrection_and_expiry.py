import pytest
import tempfile
import os
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from core.voucher_lifecycle import parse_vietnam_time, VN_TZ, evaluate_lifecycle_transition
from app.core.junk_filter import validate_voucher
from core.elite_voucher_filter import is_elite_voucher
from sources.telegram_channel_source import TelegramChannelSource
from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus, VerificationStatus
from repositories.voucher_repository import VoucherRepository
from repositories.scan_repository import ScanRepository
from repositories.shop_repository import ShopRepository
from services.dedupe_service import DedupeService
from services.lifecycle_service import LifecycleService
from services.elite_notification_service import EliteNotificationService

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.remove(path)

# 1. TelegramChannelSource bỏ qua tin nhắn cũ hơn 48h
def test_telegram_source_ignores_messages_older_than_48h():
    source = TelegramChannelSource()
    old_time = (datetime.now(VN_TZ) - timedelta(days=15)).strftime("%Y-%m-%dT%H:%M:%S+07:00")
    html = f"""
    <div class="tgme_widget_message" data-post="magiamgiashopee/1234">
        <time datetime="{old_time}">12:00</time>
        <div class="tgme_widget_message_text" dir="auto">
            🔥 Nhập mã <code>SALE50K0D</code> giảm 50k đơn từ 0đ toàn sàn lúc 12h!
            <a href="https://s.shopee.vn/test1234">Link</a>
        </div>
    </div>
    """
    item = source._parse_message(html, "magiamgiashopee")
    assert item is None

# 2. TelegramChannelSource nhận tin nhắn mới và gắn ngày của bài viết (không gán now)
def test_telegram_source_accepts_fresh_messages():
    source = TelegramChannelSource()
    post_time = datetime.now(VN_TZ) - timedelta(hours=3)
    post_time_iso = post_time.strftime("%Y-%m-%dT%H:%M:%S+07:00")
    html = f"""
    <div class="tgme_widget_message" data-post="magiamgiashopee/5678">
        <time datetime="{post_time_iso}">15:00</time>
        <div class="tgme_widget_message_text" dir="auto">
            🔥 Nhập mã <code>SALE100K0D</code> giảm 100k đơn từ 0đ lúc 20h!
            <a href="https://s.shopee.vn/test5678">Link</a>
        </div>
    </div>
    """
    item = source._parse_message(html, "magiamgiashopee")
    assert item is not None
    assert item["voucher_code"] == "SALE100K0D"
    assert item["discount_value"] == 100000.0
    # Thời gian bắt đầu phải khớp với ngày đăng + 20h
    expected_date = post_time.strftime("%Y-%m-%d")
    assert f"{expected_date} 20:00:00" in item["start_time"]
    assert post_time.strftime("%Y%m%d") in item["id"]

# 3. parse_vietnam_time parse chuẩn chuỗi có ngoặc đơn
def test_parse_vietnam_time_with_parentheses():
    # Dạng '20:00 (14/10)'
    dt1 = parse_vietnam_time("20:00 (14/10)")
    assert dt1 is not None
    assert dt1.hour == 20
    assert dt1.minute == 0
    assert dt1.day == 14
    assert dt1.month == 10

    # Dạng '15:30 (29/09/2026)'
    dt2 = parse_vietnam_time("15:30 (29/09/2026)")
    assert dt2 is not None
    assert dt2.hour == 15
    assert dt2.minute == 30
    assert dt2.day == 29
    assert dt2.month == 9
    assert dt2.year == 2026

# 4. parse_vietnam_time không nhảy năm vô tội vạ cho ngày tháng trước
def test_parse_vietnam_time_no_spurious_year_rollover():
    # Tin bài ngày 29/09 quét vào tháng 10 năm 2026 phải giữ năm 2026 (quá khứ), không được nhảy sang 2027
    dt = parse_vietnam_time("20:00 (29/09)")
    assert dt is not None
    assert dt.month == 9
    assert dt.day == 29
    now = datetime.now(VN_TZ)
    assert dt.year == now.year
    assert dt < now  # Đã qua hạn trong quá khứ

# 5. junk_filter fail-closed với ngày không hợp lệ hoặc đã qua hạn
def test_junk_filter_fail_closed_on_corrupt_date():
    # Ngày không parse được -> Fail
    v_corrupt = {"end_time": "INVALID_CORRUPT_TIME", "discount_value": 50000}
    is_valid, reason = validate_voucher(v_corrupt)
    assert is_valid is False
    assert "không parse được" in reason

    # Ngày trong quá khứ -> Fail
    v_past = {"end_time": "2026-09-29 20:00:00", "discount_value": 50000}
    is_valid, reason = validate_voucher(v_past)
    assert is_valid is False
    assert "quá hạn" in reason

# 6. elite_voucher_filter chặn voucher đã hết hạn
def test_elite_voucher_filter_blocks_expired():
    v_expired = {
        "voucher_code": "EXPIRED100",
        "verification_status": "VERIFIED_ACTIVE",
        "start_time": "2026-09-29 20:00:00",
        "end_time": "2026-09-29 20:30:00",
        "discount_type": "FIXED",
        "discount_value": 100000.0,
        "min_order_value": 0.0,
        "source_url": "https://shopee.vn"
    }
    worthy, reason = is_elite_voucher(v_expired)
    assert worthy is False
    assert "hết hạn" in reason

# 7. lifecycle_service âm thầm chuyển EXPIRED và KHÔNG BAO GIỜ gửi thông báo khi mã hết hạn
def test_lifecycle_service_silently_expires_old_vouchers(temp_db):
    v_repo = VoucherRepository(temp_db)
    s_repo = ScanRepository(temp_db)
    shop_repo = ShopRepository(temp_db)
    dedupe = DedupeService(s_repo)

    # Voucher đã hết hạn 3 ngày trước
    past_end = (datetime.now(VN_TZ) - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
    past_start = (datetime.now(VN_TZ) - timedelta(days=3, hours=1)).strftime("%Y-%m-%d %H:%M:%S")

    v = Voucher(
        id="V_PAST_TEST",
        platform="SHOPEE",
        voucher_code="PAST100",
        title="Mã Đã Hết Hạn",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=100000,
        min_order_value=0,
        start_time=past_start,
        end_time=past_end,
        source_url="https://shopee.vn",
        source_type="AFFILIATE_NETWORK",
        status=VoucherStatus.ACTIVE,
        verification_status=VerificationStatus.VERIFIED_ACTIVE
    )
    v_repo.upsert(v)

    svc = LifecycleService(voucher_repo=v_repo, scan_repo=s_repo, dedupe_service=dedupe, shop_repo=shop_repo)
    notifs = svc.run_lifecycle_cycle()

    # Tuyệt đối không có thông báo VOUCHER_EXPIRED
    expired_notifs = [n for n in notifs if n.get("type") == "VOUCHER_EXPIRED"]
    assert len(expired_notifs) == 0

    # Trạng thái trong DB phải được cập nhật sang EXPIRED
    db_v = v_repo.get_by_id("V_PAST_TEST")
    assert db_v.status == VoucherStatus.EXPIRED

# 8. Ghi nhận dedupe ngay lập tức chống race condition
def test_lifecycle_immediate_dedupe_recording(temp_db):
    v_repo = VoucherRepository(temp_db)
    s_repo = ScanRepository(temp_db)
    shop_repo = ShopRepository(temp_db)
    dedupe = DedupeService(s_repo)

    now = datetime.now(VN_TZ)
    v = Voucher(
        id="V_ACTIVE_NOW",
        platform="SHOPEE",
        voucher_code="NOW100",
        title="Mã Vừa Mở 100k",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=100000,
        min_order_value=0,
        start_time=(now - timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S"),
        end_time=(now + timedelta(minutes=25)).strftime("%Y-%m-%d %H:%M:%S"),
        source_url="https://shopee.vn",
        source_type="AFFILIATE_NETWORK",
        status=VoucherStatus.UPCOMING_CODE_KNOWN,
        verification_status=VerificationStatus.VERIFIED_ACTIVE
    )
    v_repo.upsert(v)

    svc = LifecycleService(voucher_repo=v_repo, scan_repo=s_repo, dedupe_service=dedupe, shop_repo=shop_repo)

    # Chạy lần 1: Sinh thông báo VOUCHER_OPENED
    notifs1 = svc.run_lifecycle_cycle()
    opened1 = [n for n in notifs1 if n.get("type") == "VOUCHER_OPENED"]
    assert len(opened1) == 1

    # Chạy lần 2 ngay lập tức: Phải bị dedupe chặn, không sinh thêm lần 2
    notifs2 = svc.run_lifecycle_cycle()
    opened2 = [n for n in notifs2 if n.get("type") == "VOUCHER_OPENED"]
    assert len(opened2) == 0

# 9. cleanup_old_records dọn dẹp sạch sẽ bản ghi hết hạn > 7 ngày
def test_cleanup_old_records_removes_old_expired_vouchers(temp_db):
    v_repo = VoucherRepository(temp_db)
    now = datetime.now(VN_TZ)
    old_time = (now - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")

    v_old = Voucher(
        id="V_ANCIENT",
        platform="SHOPEE",
        voucher_code="ANCIENT",
        title="Mã Cũ",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=0,
        start_time=(now - timedelta(days=11)).strftime("%Y-%m-%d %H:%M:%S"),
        end_time=old_time,
        source_url="https://shopee.vn",
        source_type="AFFILIATE_NETWORK",
        status=VoucherStatus.EXPIRED,
        verification_status=VerificationStatus.INVALID
    )
    v_repo.upsert(v_old)

    res = v_repo.cleanup_old_records()
    assert res["expired_vouchers"] >= 1
    assert v_repo.get_by_id("V_ANCIENT") is None

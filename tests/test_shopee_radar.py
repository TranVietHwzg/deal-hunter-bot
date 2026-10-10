import os
import pytest
import asyncio
from datetime import datetime, timedelta, timezone

from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus
from models.scan_run import ScanMode
from repositories.base_repository import BaseRepository
from repositories.voucher_repository import VoucherRepository
from repositories.shop_repository import ShopRepository
from repositories.scan_repository import ScanRepository
from core.voucher_filter import is_freeship, is_worthy_voucher
from core.voucher_classifier import classify_scope
from core.voucher_lifecycle import (
    determine_initial_status,
    evaluate_lifecycle_transition,
    check_upcoming_reminder,
    parse_vietnam_time,
    VN_TZ
)
from core.upcoming_voucher_discovery import UpcomingVoucherDiscovery
from core.rate_limiter import RateLimiter, CircuitBreaker
from services.dedupe_service import DedupeService
from services.lifecycle_service import LifecycleService
from services.discovery_service import DiscoveryService
from app.bot.scan_controls import ScanControls
from tests.fixtures.voucher_fixtures import get_test_voucher_fixtures

TEST_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_radar.db")

@pytest.fixture(autouse=True)
def setup_test_db():
    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

    v_repo = VoucherRepository(TEST_DB_PATH)
    s_repo = ShopRepository(TEST_DB_PATH)
    sc_repo = ScanRepository(TEST_DB_PATH)

    v_repo.init_schema()
    s_repo.init_schema()
    sc_repo.init_schema()

    yield {
        "v_repo": v_repo,
        "s_repo": s_repo,
        "sc_repo": sc_repo
    }

    if os.path.exists(TEST_DB_PATH):
        try:
            os.remove(TEST_DB_PATH)
        except Exception:
            pass

# 1. Voucher freeship luôn bị loại
def test_zero_freeship_filter():
    freeship_samples = [
        {"title": "Mã Miễn Phí Vận Chuyển Toàn Sàn", "discount_value": 30000},
        {"title": "Giảm giá sâu", "description": "Hỗ trợ phí vận chuyển 25k", "discount_value": 25000},
        {"title": "Freeship Xtra Shopee", "discount_value": 50000},
        {"title": "Voucher đơn 0đ", "category": "Mã Vận Chuyển", "discount_value": 20000},
        {"title": "Giảm cước giao hàng đơn từ 50k", "discount_value": 15000}
    ]
    for sample in freeship_samples:
        is_ship, reason = is_freeship(sample)
        assert is_ship is True, f"Lẽ ra phải chặn: {sample['title']}"

    valid_voucher = {
        "title": "Mã Giảm 100k Đơn Từ 400k",
        "description": "Giảm trực tiếp giá sản phẩm",
        "category": "Điện Tử",
        "discount_value": 100000,
        "is_freeship": 0
    }
    is_ship, _ = is_freeship(valid_voucher)
    assert is_ship is False

# 2. Voucher toàn sàn và voucher shop được phân loại đúng
def test_scope_classification():
    platform_v = {"title": "Mã Toàn Sàn", "voucher_type": "PLATFORM"}
    category_v = {"title": "Mã Điện Tử", "category": "Điện Tử Công Nghệ"}
    shop_v = {"title": "Mã Shop", "shop_id": "official_samsung", "shop_name": "Samsung"}

    assert classify_scope(platform_v) == ScopeType.PLATFORM
    assert classify_scope(category_v) == ScopeType.CATEGORY
    assert classify_scope(shop_v) == ScopeType.SHOP

# 3. Mã chưa công bố không được tạo code giả
def test_unknown_code_no_fake_code(setup_test_db):
    v_repo = setup_test_db["v_repo"]
    discovery = UpcomingVoucherDiscovery(v_repo)

    raw_event = [{
        "id": "EVENT_SALE_CHUA_CO_CODE",
        "voucher_code": None,  # Chưa công bố mã
        "title": "Sự Kiện Siêu Sale Chưa Lộ Mã",
        "discount_type": "FIXED",
        "discount_value": 100000,
        "min_order_value": 500000,
        "start_time": "00:00 20/10/2026",
        "end_time": "23:59 20/10/2026",
        "confidence_score": 90
    }]

    res = discovery.process_collected_vouchers(raw_event)
    saved = v_repo.get_by_id("EVENT_SALE_CHUA_CO_CODE")
    assert saved is not None
    assert saved.voucher_code is None
    assert saved.status == VoucherStatus.UPCOMING_UNKNOWN_CODE

# 4. Mã sắp mở hiển thị đúng start_time/end_time theo Asia/Ho_Chi_Minh
def test_upcoming_time_timezone():
    t_str = "15:30 15/10/2026"
    dt = parse_vietnam_time(t_str)
    assert dt is not None
    assert dt.tzinfo == VN_TZ
    assert dt.hour == 15
    assert dt.minute == 30
    assert dt.day == 15
    assert dt.month == 10
    assert dt.year == 2026

# 5. Thay đổi start_time/end_time tạo notification update đúng một lần
def test_voucher_change_detection(setup_test_db):
    v_repo = setup_test_db["v_repo"]
    discovery = UpcomingVoucherDiscovery(v_repo)

    raw_item = [{
        "id": "SP_TEST_TIME_CHANGE",
        "voucher_code": "CHANGECODE50K",
        "title": "Mã Sắp Mở Ban Đầu",
        "discount_type": "FIXED",
        "discount_value": 50000,
        "min_order_value": 200000,
        "start_time": "00:00 12/10/2026",
        "end_time": "23:59 12/10/2026"
    }]
    discovery.process_collected_vouchers(raw_item)

    # Đổi giờ mở
    updated_item = [{
        "id": "SP_TEST_TIME_CHANGE",
        "voucher_code": "CHANGECODE50K",
        "title": "Mã Sắp Mở Đổi Giờ",
        "discount_type": "FIXED",
        "discount_value": 50000,
        "min_order_value": 200000,
        "start_time": "09:00 12/10/2026",  # Đổi giờ sang 09:00
        "end_time": "23:59 12/10/2026"
    }]
    res2 = discovery.process_collected_vouchers(updated_item)
    assert res2["updated_vouchers"] == 1
    assert len(res2["events_to_notify"]) == 1
    assert res2["events_to_notify"][0]["type"] == "TIME_CHANGED"

# 6. Mã ACTIVE chỉ gửi một thông báo mở mã
def test_active_notification_once(setup_test_db):
    v_repo = setup_test_db["v_repo"]
    sc_repo = setup_test_db["sc_repo"]
    lifecycle = LifecycleService(v_repo, sc_repo)

    now = datetime.now(VN_TZ)
    # Voucher đã đến giờ mở: start_time vừa qua 5 phút
    v = Voucher(
        id="V_ACTIVE_TEST",
        platform="SHOPEE",
        voucher_code="ACTIVE100K",
        title="Mã Mở Bây Giờ",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=100000,
        min_order_value=300000,
        start_time=(now - timedelta(minutes=5)).strftime("%H:%M %d/%m/%Y"),
        end_time=(now + timedelta(hours=5)).strftime("%H:%M %d/%m/%Y"),
        status=VoucherStatus.UPCOMING_CODE_KNOWN,
        source_url="https://shopee.vn",
        source_type="CAMPAIGN_PAGE"
    )
    v_repo.upsert(v)

    # Lần 1: Chuyển sang ACTIVE và tạo thông báo
    notifs1 = lifecycle.run_lifecycle_cycle()
    assert len(notifs1) == 1
    assert notifs1[0]["type"] == "VOUCHER_OPENED"

    # Giả lập đã ghi log gửi thành công
    from models.notification import NotificationEvent, NotificationEventType
    sc_repo.record_notification(NotificationEvent(
        id="EV_1",
        voucher_id=v.id,
        event_type=NotificationEventType.VOUCHER_OPENED,
        content_fingerprint=notifs1[0]["fingerprint"]
    ))

    # Lần 2: Quét lại -> không được gửi trùng
    notifs2 = lifecycle.run_lifecycle_cycle()
    assert len(notifs2) == 0

# 7. Mã hết hạn chuyển EXPIRED
def test_expired_transition(setup_test_db):
    v_repo = setup_test_db["v_repo"]
    sc_repo = setup_test_db["sc_repo"]
    lifecycle = LifecycleService(v_repo, sc_repo)

    now = datetime.now(VN_TZ)
    v = Voucher(
        id="V_EXPIRED_TEST",
        platform="SHOPEE",
        voucher_code="EXPIRED50K",
        title="Mã Quá Hạn",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=200000,
        start_time=(now - timedelta(hours=5)).strftime("%H:%M %d/%m/%Y"),
        end_time=(now - timedelta(minutes=5)).strftime("%H:%M %d/%m/%Y"),  # Đã qua
        status=VoucherStatus.ACTIVE,
        source_url="https://shopee.vn",
        source_type="CAMPAIGN_PAGE"
    )
    v_repo.upsert(v)

    lifecycle.run_lifecycle_cycle()
    updated = v_repo.get_by_id("V_EXPIRED_TEST")
    assert updated.status == VoucherStatus.EXPIRED

# 8. Nút “Quét ngay” tạo scan thủ công và trả kết quả tóm tắt
@pytest.mark.anyio
async def test_manual_scan_button(setup_test_db):
    v_repo = setup_test_db["v_repo"]
    s_repo = setup_test_db["s_repo"]
    sc_repo = setup_test_db["sc_repo"]

    discovery = DiscoveryService(v_repo, sc_repo)
    controls = ScanControls(v_repo, s_repo, discovery)

    msg, markup = await controls.execute_manual_scan()
    assert "HOÀN TẤT CHU KỲ QUÉT SHOPEE" in msg or "Không phát hiện mã giảm giá mới" in msg
    assert "inline_keyboard" in markup

    last_run = sc_repo.get_latest_scan_run()
    assert last_run is not None
    assert last_run["scan_mode"] == "MANUAL_ALL"

# 9. Không gửi trùng khi dữ liệu không đổi
def test_fingerprint_deduplication(setup_test_db):
    v_repo = setup_test_db["v_repo"]
    sc_repo = setup_test_db["sc_repo"]
    dedupe = DedupeService(sc_repo)

    v = Voucher(
        id="DEDUP_VOUCHER_1",
        platform="SHOPEE",
        voucher_code="DEDUP50K",
        title="Mã Test Chống Trùng",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=200000,
        start_time="00:00 15/10/2026",
        end_time="23:59 15/10/2026",
        status=VoucherStatus.UPCOMING_CODE_KNOWN,
        source_url="https://shopee.vn",
        source_type="CAMPAIGN_PAGE"
    )
    v_repo.upsert(v)

    fp = dedupe.calculate_fingerprint(v, "NEW_CODE")
    assert dedupe.is_duplicate(fp) is False

    from models.notification import NotificationEvent, NotificationEventType
    sc_repo.record_notification(NotificationEvent(
        id="NOTIF_DEDUP_1",
        voucher_id=v.id,
        event_type=NotificationEventType.NEW_CODE,
        content_fingerprint=fp
    ))

    assert dedupe.is_duplicate(fp) is True

# 10. Rate-limit/backoff hoạt động khi nguồn lỗi
def test_rate_limiter_and_backoff():
    cb = CircuitBreaker(failure_threshold=3, recovery_time_seconds=2.0)
    assert cb.can_execute() is True

    cb.record_failure()
    assert cb.state == "CLOSED"
    assert cb.get_backoff_delay() == 2.0

    cb.record_failure()
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.can_execute() is False

# 11. Thêm/xóa shop theo dõi không ảnh hưởng dữ liệu voucher cũ
def test_tracked_shop_crud(setup_test_db):
    v_repo = setup_test_db["v_repo"]
    s_repo = setup_test_db["s_repo"]

    # Thêm 1 voucher trước
    v = Voucher(
        id="OLD_VOUCHER_SAFE",
        platform="SHOPEE",
        voucher_code="SAFE100K",
        title="Mã Không Bị Xóa",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=100000,
        min_order_value=400000,
        start_time="00:00 12/10/2026",
        end_time="23:59 12/10/2026",
        source_url="https://shopee.vn",
        source_type="CAMPAIGN_PAGE"
    )
    v_repo.upsert(v)

    # Thêm shop
    s_repo.add_shop("shop_logitech", "Logitech Official", "https://shopee.vn/shop_logitech")
    shops = s_repo.get_tracked_shops()
    assert len(shops) == 1
    assert shops[0].shop_id == "shop_logitech"

    # Xóa shop
    s_repo.remove_shop("shop_logitech")
    assert len(s_repo.get_tracked_shops()) == 0

    # Voucher cũ vẫn tồn tại nguyên vẹn
    assert v_repo.get_by_id("OLD_VOUCHER_SAFE") is not None

# 12. Dữ liệu fixture bao phủ đầy đủ các loại voucher
def test_voucher_fixtures_coverage(setup_test_db):
    fixtures = get_test_voucher_fixtures()
    assert len(fixtures) == 6

    scopes = [f.get("scope_type") for f in fixtures]
    assert "PLATFORM" in scopes
    assert "CATEGORY" in scopes
    assert "SHOP" in scopes

    # Có mã sắp mở, có sự kiện chưa lộ code, có mã hết hạn, có freeship
    has_unknown = any(f.get("voucher_code") is None for f in fixtures)
    has_freeship = any(f.get("is_freeship") == 1 for f in fixtures)
    assert has_unknown is True
    assert has_freeship is True

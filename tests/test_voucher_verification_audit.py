import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus, VerificationStatus
from core.elite_voucher_filter import is_elite_voucher
from core.elite_score_calculator import calculate_elite_score
from repositories.voucher_repository import VoucherRepository
from repositories.shop_repository import ShopRepository
from services.elite_discovery_service import EliteDiscoveryService
from app.bot.elite_commands import EliteCommands

VN_TZ = timezone(timedelta(hours=7))

# 1. Voucher fixture (TEST_DATA) không xuất hiện trong /elite
@pytest.mark.anyio
async def test_01_fixture_test_data_rejected_from_elite():
    v = Voucher(
        id="TEST_SAMPLE_1",
        voucher_code="FIXTURE100K",
        verification_status=VerificationStatus.TEST_DATA,
        title="Mã kiểm thử: Giảm 100k đơn 0đ",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=100000,
        min_order_value=0,
        start_time="00:00 11/10/2026",
        end_time="23:59 11/10/2026",
        source_url="https://shopee.vn/test",
        source_type="TEST_FIXTURE"
    )
    is_elite, reason = is_elite_voucher(v)
    assert not is_elite
    assert "TEST_DATA" in reason

# 2. Voucher không có source_url bị loại
def test_02_voucher_without_source_url_rejected():
    v = {
        "voucher_code": "NOSOURCE50K",
        "verification_status": "VERIFIED_ACTIVE",
        "discount_type": "FIXED",
        "discount_value": 50000,
        "min_order_value": 0,
        "start_time": "00:00 11/10/2026",
        "end_time": "23:59 11/10/2026",
        "source_url": "", # Thiếu source_url
        "title": "Mã không nguồn"
    }
    is_elite, reason = is_elite_voucher(v, require_evidence=True)
    assert not is_elite
    assert "source_url" in reason

# 3. Voucher không có start_time/end_time bị loại
def test_03_voucher_without_times_rejected():
    v = {
        "voucher_code": "NOTIME50K",
        "verification_status": "VERIFIED_ACTIVE",
        "discount_type": "FIXED",
        "discount_value": 50000,
        "min_order_value": 0,
        "source_url": "https://shopee.vn/valid",
        "start_time": "", # Thiếu start_time
        "end_time": "",
        "title": "Mã không thời gian"
    }
    is_elite, reason = is_elite_voucher(v, require_evidence=True)
    assert not is_elite
    assert "start_time" in reason or "thời gian" in reason

# 4. Voucher có source chính thức và thời gian tương lai là VERIFIED_UPCOMING
def test_04_verified_upcoming_voucher_accepted():
    now_vn = datetime.now(VN_TZ)
    future_start = (now_vn + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    future_end = (now_vn + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
    v = Voucher(
        id="VERIFIED_UPCOMING_1",
        voucher_code="UPCOMING50K",
        verification_status=VerificationStatus.VERIFIED_UPCOMING,
        title="Mã sắp mở: Giảm 50k đơn 100k",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=100000,
        start_time=future_start,
        end_time=future_end,
        source_url="https://shopee.vn/m/khung-gio-vang",
        source_type="CAMPAIGN_PAGE",
        status=VoucherStatus.UPCOMING_CODE_KNOWN
    )
    is_elite, reason = is_elite_voucher(v)
    assert is_elite
    assert "Đạt Elite" in reason

# 5. Voucher có nguồn chính thức và đang hiệu lực là VERIFIED_ACTIVE
def test_05_verified_active_voucher_accepted():
    now_vn = datetime.now(VN_TZ)
    active_start = (now_vn - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    active_end = (now_vn + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
    v = Voucher(
        id="VERIFIED_ACTIVE_1",
        voucher_code="REALACTIVE50K",
        verification_status=VerificationStatus.VERIFIED_ACTIVE,
        title="Mã đang chạy: Giảm 50k đơn 0đ",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=0,
        start_time=active_start,
        end_time=active_end,
        source_url="https://shopee.vn/m/ma-giam-gia",
        source_type="COMMUNITY_FEED",
        status=VoucherStatus.ACTIVE
    )
    is_elite, reason = is_elite_voucher(v)
    assert is_elite
    assert "Đạt Elite" in reason

# 6. Voucher chưa có code là UPCOMING_UNKNOWN_CODE, không phải Elite
def test_06_upcoming_unknown_code_not_elite():
    v = Voucher(
        id="EVENT_UNKNOWN_1",
        voucher_code=None, # Chưa có code
        verification_status=VerificationStatus.UPCOMING_UNKNOWN_CODE,
        title="Đại tiệc sale giữa tháng",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=100000,
        min_order_value=300000,
        start_time="00:00 15/10/2026",
        end_time="23:59 15/10/2026",
        source_url="https://shopee.vn/m/sale-giua-thang",
        source_type="CAMPAIGN_PAGE",
        status=VoucherStatus.UPCOMING_UNKNOWN_CODE
    )
    is_elite, reason = is_elite_voucher(v)
    assert not is_elite
    assert "UPCOMING_UNKNOWN_CODE" in reason or "voucher_code" in reason

# 7. Voucher không có bằng chứng là UNVERIFIED, không gửi Telegram
def test_07_unverified_voucher_rejected():
    v = Voucher(
        id="UNVERIFIED_1",
        voucher_code="UNVERIFIEDCODE",
        verification_status=VerificationStatus.UNVERIFIED,
        title="Mã trích xuất bài viết: UNVERIFIEDCODE",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=100000,
        min_order_value=0,
        start_time="00:00 11/10/2026",
        end_time="23:59 11/10/2026",
        source_url="https://bloggiamgia.vn/shopee",
        source_type="COMMUNITY_FEED"
    )
    is_elite, reason = is_elite_voucher(v)
    assert not is_elite
    assert "UNVERIFIED" in reason

# 8. Voucher có mã nhưng điều kiện tài khoản chưa kiểm tra là PERSONAL_ELIGIBILITY_UNKNOWN
def test_08_personal_eligibility_unknown_rejected():
    v = Voucher(
        id="PERSONAL_1",
        voucher_code="WALLET50K",
        verification_status=VerificationStatus.PERSONAL_ELIGIBILITY_UNKNOWN,
        title="Mã ví cá nhân: Giảm 50k",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=0,
        start_time="00:00 11/10/2026",
        end_time="23:59 11/10/2026",
        source_url="https://shopee.vn/m/wallet",
        source_type="PAYMENT_PARTNER"
    )
    is_elite, reason = is_elite_voucher(v)
    assert not is_elite
    assert "PERSONAL_ELIGIBILITY_UNKNOWN" in reason

# 9. Voucher hết hạn là INVALID hoặc EXPIRED, không gửi alert
def test_09_expired_invalid_voucher_rejected():
    v = Voucher(
        id="EXPIRED_1",
        voucher_code="EXPIRED50K",
        verification_status=VerificationStatus.INVALID,
        title="Mã hết hạn",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=0,
        start_time="00:00 01/10/2026",
        end_time="23:59 05/10/2026",
        source_url="https://shopee.vn",
        source_type="CAMPAIGN_PAGE",
        status=VoucherStatus.EXPIRED
    )
    is_elite, reason = is_elite_voucher(v)
    assert not is_elite
    assert "INVALID" in reason or "EXPIRED" in reason

# 10. Voucher test/mock/seed bị loại hoàn toàn khỏi production elite
@pytest.mark.anyio
async def test_10_test_data_excluded_from_elite_query():
    repo = VoucherRepository()
    test_v = Voucher(
        id="TEST_SEED_FOR_QUERY",
        voucher_code="TESTSEED100K",
        verification_status=VerificationStatus.TEST_DATA,
        title="Test seed",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=100000,
        min_order_value=0,
        start_time="00:00 11/10/2026",
        end_time="23:59 11/10/2026",
        source_url="https://shopee.vn",
        source_type="TEST_DATA"
    )
    repo.upsert(test_v)
    elite_list = repo.get_elite_verified_vouchers()
    assert all(x.id != "TEST_SEED_FOR_QUERY" for x in elite_list)
    assert all(x.verification_status != VerificationStatus.TEST_DATA for x in elite_list)
    
    # Dọn dẹp
    with repo.transaction() as cur:
        cur.execute("DELETE FROM vouchers WHERE id = 'TEST_SEED_FOR_QUERY'")

# 11. /verify, /source, /status trả đúng nguồn, shop, thời gian và mức xác minh
@pytest.mark.anyio
async def test_11_verify_source_status_commands():
    v_repo = VoucherRepository()
    s_repo = ShopRepository()
    discovery = EliteDiscoveryService(v_repo, None, s_repo)
    commands = EliteCommands(v_repo, s_repo, discovery)

    v = Voucher(
        id="TEST_VERIFY_SAMPLE",
        voucher_code="AUDITPCU35",
        verification_status=VerificationStatus.VERIFIED_ACTIVE,
        title="Mã Điện Tử: Giảm 35% tối đa 120k",
        scope_type=ScopeType.SHOP,
        shop_id="12345",
        shop_name="Anker Official",
        shop_url="https://shopee.vn/anker",
        discount_type=DiscountType.PERCENT,
        discount_value=35,
        max_discount=120000,
        min_order_value=0,
        start_time="00:00 11/10/2026",
        end_time="23:59 31/10/2026",
        source_url="https://shopee.vn/voucher/details?promo=123",
        source_type="COMMUNITY_FEED",
        source_title="Shopee Hub Portal",
        source_evidence_excerpt="Mã giảm 35% tối đa 120k đơn từ 0đ tại Shop Anker",
        status=VoucherStatus.ACTIVE
    )
    v_repo.upsert(v)

    # Test /verify
    verify_resp = await commands.handle_verify_command("/verify AUDITPCU35")
    assert "VERIFIED_ACTIVE" in verify_resp
    assert "AUDITPCU35" in verify_resp
    assert "Anker Official" in verify_resp
    assert "https://shopee.vn/voucher/details?promo=123" in verify_resp

    # Test /source
    source_resp = await commands.handle_source_command("/source AUDITPCU35")
    assert "Shopee Hub Portal" in source_resp
    assert "https://shopee.vn/voucher/details?promo=123" in source_resp
    assert "Anker Official" in source_resp

    # Test /status
    status_resp = await commands.handle_status_command("/status AUDITPCU35")
    assert "VERIFIED_ACTIVE" in status_resp
    assert "ACTIVE" in status_resp

    # Test /audit
    audit_resp = await commands.handle_audit_command()
    assert "BÁO CÁO KIỂM TOÁN TÍNH THẬT" in audit_resp
    assert "VERIFIED_ACTIVE" in audit_resp

    # Dọn dẹp
    with v_repo.transaction() as cur:
        cur.execute("DELETE FROM vouchers WHERE id = 'TEST_VERIFY_SAMPLE'")

# 12. Không có câu "Sẵn sàng dùng" nếu chưa xác minh được khả năng áp dụng
def test_12_no_ready_to_use_without_personal_verification():
    from app.bot.elite_templates import format_verified_active_voucher, format_verified_upcoming_voucher, format_upcoming_unknown_event
    v_active = Voucher(
        id="V_ACT",
        voucher_code="CODE1",
        verification_status=VerificationStatus.VERIFIED_ACTIVE,
        title="Active",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=0,
        start_time="00:00 11/10/2026",
        end_time="23:59 11/10/2026",
        source_url="https://shopee.vn",
        source_type="COMMUNITY_FEED"
    )
    msg, _ = format_verified_active_voucher(v_active)
    assert "Sẵn sàng dùng" not in msg

    v_unknown = Voucher(
        id="V_UNK",
        voucher_code=None,
        verification_status=VerificationStatus.UPCOMING_UNKNOWN_CODE,
        title="Event",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=0,
        start_time="00:00 11/10/2026",
        end_time="23:59 11/10/2026",
        source_url="https://shopee.vn",
        source_type="CAMPAIGN_PAGE"
    )
    msg_ev, _ = format_upcoming_unknown_event(v_unknown)
    assert "Sẵn sàng dùng" not in msg_ev
    assert "Chưa phải voucher xác minh" in msg_ev

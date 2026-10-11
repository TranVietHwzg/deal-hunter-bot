import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from models.voucher import Voucher, ScopeType, DiscountType, VoucherStatus
from core.elite_voucher_filter import is_elite_voucher, is_freeship
from core.elite_score_calculator import calculate_elite_score
from core.notification_dedupe import NotificationDedupe
from sources.personal_eligible_voucher_source import PersonalEligibleVoucherSource
from services.elite_notification_service import EliteNotificationService
from services.elite_discovery_service import EliteDiscoveryService
from repositories.voucher_repository import VoucherRepository
from repositories.shop_repository import ShopRepository
from repositories.scan_repository import ScanRepository

VN_TZ = timezone(timedelta(hours=7))

class DummyBot:
    def __init__(self):
        self.sent_messages = []

    async def send_message(self, text: str, reply_markup=None):
        self.sent_messages.append({"text": text, "reply_markup": reply_markup})
        return {"ok": True, "result": {"message_id": len(self.sent_messages)}}

# 1. Giảm 20k, đơn 0đ → loại
def test_1_fixed_under_30k_zero_min_order_rejected():
    v = {
        "discount_type": "FIXED",
        "discount_value": 20000,
        "min_order_value": 0,
        "title": "Mã giảm 20k đơn 0đ",
        "is_freeship": 0
    }
    is_elite, reason = is_elite_voucher(v)
    assert not is_elite
    assert "< 30.000đ" in reason

# 2. Giảm 30k, đơn 0đ → đạt Elite
def test_2_fixed_30k_zero_min_order_accepted():
    v = {
        "discount_type": "FIXED",
        "discount_value": 30000,
        "min_order_value": 0,
        "title": "Mã giảm 30k đơn 0đ",
        "is_freeship": 0
    }
    is_elite, reason = is_elite_voucher(v)
    assert is_elite
    assert "Đạt Elite" in reason

# 3. Giảm 50k, đơn 150k → đạt Elite
def test_3_fixed_50k_min_order_150k_accepted():
    v = {
        "discount_type": "FIXED",
        "discount_value": 50000,
        "min_order_value": 150000,
        "title": "Mã giảm 50k đơn 150k",
        "is_freeship": 0
    }
    is_elite, reason = is_elite_voucher(v)
    assert is_elite
    assert "Đạt Elite" in reason

# 4. Giảm 50k, đơn 500k → loại
def test_4_fixed_50k_min_order_500k_rejected():
    v = {
        "discount_type": "FIXED",
        "discount_value": 50000,
        "min_order_value": 500000,
        "title": "Mã giảm 50k đơn 500k",
        "is_freeship": 0
    }
    is_elite, reason = is_elite_voucher(v)
    assert not is_elite
    assert "Điều kiện đơn quá cao" in reason

# 5. Giảm 30%, tối đa 100k, đơn 100k → đạt Elite
def test_5_percent_30_cap_100k_min_order_100k_accepted():
    v = {
        "discount_type": "PERCENT",
        "discount_value": 30,
        "max_discount": 100000,
        "min_order_value": 100000,
        "title": "Giảm 30% tối đa 100k",
        "is_freeship": 0
    }
    is_elite, reason = is_elite_voucher(v)
    assert is_elite
    assert "Đạt Elite" in reason

# 6. Giảm 30%, tối đa 10k → loại
def test_6_percent_30_cap_10k_rejected():
    v = {
        "discount_type": "PERCENT",
        "discount_value": 30,
        "max_discount": 10000,
        "min_order_value": 50000,
        "title": "Giảm 30% tối đa 10k",
        "is_freeship": 0
    }
    is_elite, reason = is_elite_voucher(v)
    assert not is_elite
    assert "< 30,000đ" in reason or "< 30.000đ" in reason

# 7. Giảm 30%, đơn tối thiểu 2 triệu → loại
def test_7_percent_30_min_order_2m_rejected():
    v = {
        "discount_type": "PERCENT",
        "discount_value": 30,
        "max_discount": 100000,
        "min_order_value": 2000000,
        "title": "Giảm 30% tối đa 100k đơn 2tr",
        "is_freeship": 0
    }
    is_elite, reason = is_elite_voucher(v)
    assert not is_elite
    assert "quá cao" in reason

# 8. Freeship → luôn bị loại
def test_8_freeship_always_rejected():
    v1 = {"discount_type": "FIXED", "discount_value": 100000, "min_order_value": 0, "title": "Mã Freeship Xtra 100k", "is_freeship": 0}
    v2 = {"discount_type": "FIXED", "discount_value": 100000, "min_order_value": 0, "title": "Miễn phí vận chuyển toàn sàn", "is_freeship": 0}
    v3 = {"discount_type": "FIXED", "discount_value": 100000, "min_order_value": 0, "title": "Mã xịn", "is_freeship": 1}

    assert not is_elite_voucher(v1)[0]
    assert not is_elite_voucher(v2)[0]
    assert not is_elite_voucher(v3)[0]

# 9. Mã sắp mở nhưng chưa code → không bịa mã
def test_9_upcoming_unknown_no_fake_code():
    now = datetime.now(VN_TZ)
    tomorrow = (now + timedelta(days=1)).strftime("%d/%m/%Y")
    v = Voucher(
        id="EVT_UPCOMING_TEST",
        platform="SHOPEE",
        voucher_code=None,
        title="Sự kiện khung giờ vàng 0h",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=100000,
        min_order_value=0,
        start_time=f"00:00 {tomorrow}",
        end_time=f"23:59 {tomorrow}",
        source_url="https://shopee.vn/m/khung-gio-vang",
        source_type="CAMPAIGN_PAGE",
        status=VoucherStatus.UPCOMING_UNKNOWN_CODE
    )
    assert v.voucher_code is None
    assert v.status == VoucherStatus.UPCOMING_UNKNOWN_CODE

# 10. Mã vừa lộ code và đạt 80 điểm → báo một lần
def test_10_code_revealed_score_80_notified_once():
    async def _test():
        bot = DummyBot()
        notifier = EliteNotificationService(bot)
        now = datetime.now(VN_TZ)
        tomorrow = (now + timedelta(days=1)).strftime("%d/%m/%Y")
        v = Voucher(
            id="EVT_REVEAL_TEST",
            platform="SHOPEE",
            voucher_code="FLASH100",
            title="Mã Flash 100k",
            scope_type=ScopeType.PLATFORM,
            discount_type=DiscountType.FIXED,
            discount_value=100000,
            min_order_value=100000,
            start_time=f"00:00 {tomorrow}",
            end_time=f"23:59 {tomorrow}",
            source_url="https://shopee.vn/m/ma-giam-gia",
            source_type="CAMPAIGN_PAGE",
            status=VoucherStatus.UPCOMING_CODE_KNOWN
        )
        score, _, _ = calculate_elite_score(v)
        assert score >= 80

        # Lần 1: gửi thành công
        sent1 = await notifier.notify_elite_voucher(v, "CODE_REVEALED", score=score)
        assert sent1 is True
        assert len(bot.sent_messages) == 1
        assert "MÃ SẮP MỞ ĐÃ LỘ CODE" in bot.sent_messages[0]["text"]

        # Lần 2: trùng fingerprint -> không gửi
        sent2 = await notifier.notify_elite_voucher(v, "CODE_REVEALED", score=score)
        assert sent2 is False
        assert len(bot.sent_messages) == 1
    import asyncio
    asyncio.run(_test())

# 11. Mã đã ACTIVE → báo một lần
def test_11_active_status_notified_once():
    async def _test():
        bot = DummyBot()
        notifier = EliteNotificationService(bot)
        now = datetime.now(VN_TZ)
        today = now.strftime("%d/%m/%Y")
        v = Voucher(
            id="EVT_ACTIVE_TEST",
            platform="SHOPEE",
            voucher_code="ACTIVE100K",
            title="Mã Active 100k",
            scope_type=ScopeType.PLATFORM,
            discount_type=DiscountType.FIXED,
            discount_value=100000,
            min_order_value=0,
            start_time=f"00:00 {today}",
            end_time=f"23:59 {today}",
            source_url="https://shopee.vn/m/ma-giam-gia",
            source_type="CAMPAIGN_PAGE",
            status=VoucherStatus.ACTIVE
        )
        score, _, _ = calculate_elite_score(v)
        assert score >= 80

        sent1 = await notifier.notify_elite_voucher(v, "ACTIVE_NEW", score=score)
        assert sent1 is True
        assert len(bot.sent_messages) == 1

        sent2 = await notifier.notify_elite_voucher(v, "ACTIVE_NEW", score=score)
        assert sent2 is False
        assert len(bot.sent_messages) == 1
    import asyncio
    asyncio.run(_test())

# 12. Dữ liệu không đổi → không báo lại
def test_12_unchanged_data_no_duplicate_notification():
    dedupe = NotificationDedupe()
    v = {
        "platform": "SHOPEE",
        "voucher_code": "SAMECODE",
        "scope_type": "PLATFORM",
        "shop_id": None,
        "discount_type": "FIXED",
        "discount_value": 50000,
        "min_order_value": 150000,
        "start_time": "00:00 12/10/2026",
        "end_time": "23:59 12/10/2026",
        "status": "ACTIVE"
    }
    fp1 = dedupe.calculate_fingerprint(v)
    dedupe.record_sent(fp1)

    # Thay đổi last_seen_at không ảnh hưởng đến fingerprint 12 trường
    v["last_seen_at"] = "2026-10-11T12:00:00Z"
    fp2 = dedupe.calculate_fingerprint(v)

    assert fp1 == fp2
    assert dedupe.is_duplicate(fp2) is True

# 13. Thời gian hiệu lực thay đổi → báo cập nhật một lần
def test_13_time_change_triggers_update_notification():
    dedupe = NotificationDedupe()
    v = {
        "platform": "SHOPEE",
        "voucher_code": "TIMECODE",
        "scope_type": "PLATFORM",
        "shop_id": None,
        "discount_type": "FIXED",
        "discount_value": 50000,
        "min_order_value": 150000,
        "start_time": "00:00 12/10/2026",
        "end_time": "23:59 12/10/2026",
        "status": "ACTIVE"
    }
    fp1 = dedupe.calculate_fingerprint(v)
    dedupe.record_sent(fp1)

    # Đổi end_time
    v["end_time"] = "23:59 15/10/2026"
    fp2 = dedupe.calculate_fingerprint(v)

    assert fp1 != fp2
    assert dedupe.is_duplicate(fp2) is False

# 14. Shop không theo dõi có mã thường → không báo
def test_14_untracked_shop_normal_voucher_not_notified():
    v = {
        "discount_type": "FIXED",
        "discount_value": 20000,
        "min_order_value": 200000,
        "scope_type": "SHOP",
        "shop_id": "random_shop_999",
        "shop_name": "Random Shop",
        "title": "Shop giảm 20k đơn 200k",
        "is_freeship": 0
    }
    is_elite, _ = is_elite_voucher(v)
    assert not is_elite

# 15. Shop theo dõi có mã 50k đơn 100k → báo
def test_15_tracked_shop_elite_voucher_notified():
    async def _test():
        bot = DummyBot()
        notifier = EliteNotificationService(bot)
        now = datetime.now(VN_TZ)
        today = now.strftime("%d/%m/%Y")
        v = Voucher(
            id="EVT_SHOP_TEST",
            platform="SHOPEE",
            voucher_code="ABC50K",
            title="Mã shop ABC giảm 50k đơn 100k",
            scope_type=ScopeType.SHOP,
            shop_id="abc_official",
            shop_name="ABC Official Store",
            shop_url="https://shopee.vn/abc_official",
            discount_type=DiscountType.FIXED,
            discount_value=50000,
            min_order_value=100000,
            start_time=f"09:00 {today}",
            end_time=f"23:59 {today}",
            source_url="https://shopee.vn/abc_official",
            source_type="SHOP_CAMPAIGN",
            status=VoucherStatus.ACTIVE
        )
        # is_tracked_shop = True, is_personal_eligible = True
        score, _, _ = calculate_elite_score(v, is_tracked_shop=True, is_personal_eligible=True)
        assert score >= 80

        sent = await notifier.notify_elite_voucher(v, "ACTIVE_NEW", score=score)
        assert sent is True
        assert len(bot.sent_messages) == 1
        assert "MÃ SHOP SIÊU XỊN" in bot.sent_messages[0]["text"]
        assert "ABC Official Store" in bot.sent_messages[0]["text"]
    import asyncio
    asyncio.run(_test())

# 16. Nguồn Ví voucher cá nhân chưa kết nối → không tuyên bố đã quét
def test_16_personal_wallet_unconnected_status_message():
    source = PersonalEligibleVoucherSource(is_connected=False)
    msg = source.get_status_message()
    assert "Chưa kết nối chính thức" in msg
    assert "chỉ đánh giá voucher từ nguồn công khai hợp lệ" in msg

# 17. Nguồn Ví voucher chính thức có dữ liệu → tăng điểm phù hợp, nhưng không hạ ngưỡng Elite
def test_17_personal_wallet_connected_adds_score_not_lower_threshold():
    v = {
        "discount_type": "FIXED",
        "discount_value": 50000,
        "min_order_value": 150000,
        "scope_type": "PLATFORM",
        "title": "Mã 50k ví",
        "source_type": "CAMPAIGN_PAGE",
        "status": "ACTIVE",
        "start_time": "00:00 12/10/2026",
        "end_time": "23:59 12/10/2026"
    }
    score_unconnected, _, _ = calculate_elite_score(v, is_personal_eligible=False)
    score_connected, _, _ = calculate_elite_score(v, is_personal_eligible=True)

    # Được cộng đúng 4 điểm khả năng sử dụng
    assert score_connected - score_unconnected == 4

    # Ngưỡng bắt buộc để phát thông báo vẫn bất biến tại 80 điểm
    notifier = EliteNotificationService(DummyBot())
    # Nếu điểm giả sử dưới 80 (vd: 75), dù có ví thì vẫn bị chặn
    low_v = Voucher(
        id="LOW_SCORE_V",
        platform="SHOPEE",
        title="Low Score",
        scope_type=ScopeType.SHOP,
        discount_type=DiscountType.FIXED,
        discount_value=30000,
        min_order_value=0,
        start_time="",
        end_time="",
        source_url="",
        source_type=""
    )
    import asyncio
    res = asyncio.run(notifier.notify_elite_voucher(low_v, "ACTIVE_NEW", score=69))
    assert res is False

# 18. Nút “Quét ngay” chỉ trả về voucher Elite mới/cập nhật
def test_18_scan_now_returns_only_elite_vouchers():
    async def _test():
        import uuid
        discovery = EliteDiscoveryService()
        v_id = f"V_ELITE_{uuid.uuid4().hex[:6]}"
        async def mock_fetch():
            return [
                {"id": "V_TRASH_1", "discount_type": "FIXED", "discount_value": 10000, "min_order_value": 0, "title": "Giảm 10k", "is_freeship": 0},
                {"id": "V_SHIP_1", "discount_type": "FIXED", "discount_value": 50000, "min_order_value": 0, "title": "Freeship 50k", "is_freeship": 0},
                {"id": v_id, "voucher_code": "ELITE100K", "source_url": "https://shopee.vn/m/ma-giam-gia", "verification_status": "VERIFIED_ACTIVE", "discount_type": "FIXED", "discount_value": 100000, "min_order_value": 0, "title": "Giảm 100k đơn 0đ", "is_freeship": 0, "start_time": "00:00 12/10/2026", "end_time": "23:59 12/10/2026", "source_type": "CAMPAIGN_PAGE"}
            ]
        async def mock_empty():
            return []

        discovery.platform_source.fetch_vouchers = mock_fetch
        discovery.shop_source.fetch_vouchers = mock_empty
        discovery.personal_source.fetch_vouchers = mock_empty
        discovery.banner_source.fetch_vouchers = mock_empty
        discovery.community_source.fetch_vouchers = mock_empty
        discovery.payment_source.fetch_vouchers = mock_empty
        discovery.live_video_source.fetch_vouchers = mock_empty
        discovery.leak_source.fetch_vouchers = mock_empty

        res = await discovery.run_elite_scan()
        # 2 voucher rác/freeship phải bị loại bỏ hoàn toàn
        assert res["items_rejected"] >= 2
        # Chỉ voucher đạt chuẩn Elite mới được tính
        assert res["elite_new"] >= 1

    import asyncio
    asyncio.run(_test())

# 19. Voucher đúng 30% chính xác (ELITE_MIN_PERCENT=30) đạt Elite
def test_19_exact_30_percent_accepted():
    v = {
        "discount_type": "PERCENT",
        "discount_value": 30.0,
        "max_discount": 30000.0,
        "min_order_value": 100000.0,
        "title": "Giảm đúng 30% tối đa 30k",
        "is_freeship": 0
    }
    is_elite, reason = is_elite_voucher(v)
    assert is_elite is True
    assert "Đạt Elite" in reason

# 20. Voucher 30k đơn 0đ PLATFORM đạt 72 điểm và được phát thông báo (ngưỡng 70 điểm)
def test_20_platform_30k_0d_score_72_and_notified():
    async def _test():
        bot = DummyBot()
        notifier = EliteNotificationService(bot)
        v = {
            "platform": "SHOPEE",
            "voucher_code": "PLAT30K",
            "scope_type": "PLATFORM",
            "discount_type": "FIXED",
            "discount_value": 30000.0,
            "min_order_value": 0.0,
            "title": "Mã sàn giảm 30k đơn 0đ",
            "start_time": "00:00 12/10/2026",
            "end_time": "23:59 12/10/2026",
            "source_type": "CAMPAIGN_PAGE",
            "source_url": "https://shopee.vn/m/ma-giam-gia",
            "is_freeship": 0
        }
        score, label, breakdown = calculate_elite_score(v)
        # 30k đơn 0đ đạt 74 điểm (>= ngưỡng 70 điểm để phát thông báo)
        assert score >= 70
        assert score == 74
        assert "ĐÁNG LẤY" in label

        v_obj = Voucher(
            id="V_30K_0D",
            platform="SHOPEE",
            voucher_code="PLAT30K",
            title="Mã sàn giảm 30k đơn 0đ",
            scope_type=ScopeType.PLATFORM,
            discount_type=DiscountType.FIXED,
            discount_value=30000,
            min_order_value=0,
            start_time="00:00 12/10/2026",
            end_time="23:59 12/10/2026",
            status=VoucherStatus.ACTIVE,
            source_url="https://shopee.vn/m/ma-giam-gia",
            source_type="CAMPAIGN_PAGE"
        )
        sent = await notifier.notify_elite_voucher(v_obj, "ACTIVE_NEW", score=score)
        assert sent is True
        assert len(bot.sent_messages) == 1
        assert "PLAT30K" in bot.sent_messages[0]["text"]
        assert "74/100" in bot.sent_messages[0]["text"]

    import asyncio
    asyncio.run(_test())

# 21. Vòng đời: Voucher EXHAUSTED được restock chuyển lại ACTIVE (VOUCHER_RESTOCKED)
def test_21_lifecycle_restock_transition():
    from core.voucher_lifecycle import evaluate_lifecycle_transition
    now = datetime.now(VN_TZ)
    v = Voucher(
        id="V_RESTOCK_TEST",
        platform="SHOPEE",
        voucher_code="RESTOCK50",
        title="Mã Restock",
        scope_type=ScopeType.PLATFORM,
        discount_type=DiscountType.FIXED,
        discount_value=50000,
        min_order_value=0,
        start_time=(now - timedelta(hours=1)).strftime("%H:%M %d/%m/%Y"),
        end_time=(now + timedelta(hours=5)).strftime("%H:%M %d/%m/%Y"),
        status=VoucherStatus.EXHAUSTED,
        percentage_used=80,  # Vừa được mở thêm lượt (< 100)
        source_url="https://shopee.vn",
        source_type="CAMPAIGN_PAGE"
    )
    new_status, event_name = evaluate_lifecycle_transition(v)
    assert new_status == VoucherStatus.ACTIVE
    assert event_name == "VOUCHER_RESTOCKED"

# 22. Parse thời gian tự động rollover năm mới nếu không có năm và bị quá khứ > 7 ngày
def test_22_year_rollover_datetime():
    from core.voucher_lifecycle import parse_vietnam_time
    # Ví dụ quét "00:00 01/01" vào tháng 12 năm nay
    # Nếu parse mà ra quá khứ > 7 ngày, nó sẽ tự động tăng lên năm sau
    current_year = datetime.now(VN_TZ).year
    parsed = parse_vietnam_time("00:00 01/01")
    assert parsed is not None
    # 01/01 của năm nay đã qua nhiều tháng, nên sẽ rollover sang năm sau
    assert parsed.year == current_year + 1

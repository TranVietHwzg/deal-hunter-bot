import pytest
from app.bot.templates import format_hot_voucher_alert
from app.bot.telegram_service import TelegramBotService
from core import database

@pytest.fixture(autouse=True)
def setup_test_hidden_vouchers():
    database.init_db()
    # Thêm dữ liệu kiểm thử độc lập cho mã ẩn
    database.upsert_voucher({
        "voucher_id": "TEST_SIEUHOI_110K",
        "voucher_code": "SIEUHOI110K",
        "title": "Mã Ẩn: SIÊU HỘI SHOPEE Giảm 110,000đ Đơn từ 0đ",
        "category": "SIÊU HỘI",
        "discount_value": 110000,
        "discount_type": "FIXED",
        "min_spend": 0.0,
        "is_hidden": 1
    })
    database.upsert_voucher({
        "voucher_id": "TEST_HIDDEN_50K",
        "voucher_code": "HIDDEN50K",
        "title": "Mã Ẩn: Giảm 50k đơn 150k",
        "category": "MÃ ẨN",
        "discount_value": 50000,
        "discount_type": "FIXED",
        "min_spend": 150000.0,
        "is_hidden": 1
    })

def test_hidden_voucher_priority_ranking():
    hidden_vouchers = database.get_vouchers(hidden_only=True)
    assert len(hidden_vouchers) >= 2
    
    # Mã có min_spend = 0đ hoặc giảm lớn phải được xếp lên đầu
    top_v = hidden_vouchers[0]
    assert top_v["is_hidden"] == 1
    assert top_v["min_spend"] == 0.0

def test_hidden_voucher_template_formatting():
    v = database.get_voucher_by_id("TEST_SIEUHOI_110K")
    assert v is not None
    msg = format_hot_voucher_alert(v)
    assert "SIEUHOI110K" in msg
    assert "Giảm 110,000đ" in msg
    assert "Đơn từ 0đ" in msg
    assert "chạm để sao chép" in msg

@pytest.mark.anyio
async def test_cmd_hidden_vouchers():
    bot = TelegramBotService()
    sent_msgs = []
    async def mock_msg(text, reply_markup=None):
        sent_msgs.append((text, reply_markup))
        return {"ok": True}
    bot.send_message = mock_msg

    await bot._cmd_hidden_vouchers()
    assert len(sent_msgs) == 1
    text, markup = sent_msgs[0]
    assert "KHO MÃ ẨN NHẬP TAY" in text
    assert "SIEUHOI110K" in text
    assert any("Mở Shopee" in b["text"] for row in markup["inline_keyboard"] for b in row)

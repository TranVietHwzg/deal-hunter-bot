import pytest
from app.bot.templates import format_hot_voucher_alert
from app.bot.telegram_service import TelegramBotService
from core import database

def test_hidden_voucher_priority_ranking():
    database.init_db()
    # 1. Lấy danh sách voucher với hidden_only = True
    hidden_vouchers = database.get_vouchers(hidden_only=True)
    assert len(hidden_vouchers) >= 4
    
    # Mã đầu tiên phải là mã ẩn có min_spend = 0đ (như SIEUHOISHOPEEOCTR)
    top_v = hidden_vouchers[0]
    assert top_v["is_hidden"] == 1
    assert top_v["min_spend"] == 0.0
    assert "SIEUHOI" in top_v["voucher_code"] or "SIÊU HỘI" in top_v.get("category", "")

def test_hidden_voucher_template_formatting():
    v = database.get_voucher_by_id("SIEUHOISHOPEEOCTR")
    assert v is not None
    msg = format_hot_voucher_alert(v)
    assert "SIEUHOISHOPEEOCTR" in msg
    assert "Giảm 110,000đ" in msg
    assert "Đơn từ 0đ" in msg
    assert "SIÊU HỘI SHOPEE" in msg
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
    assert "SIEUHOISHOPEEOCTR" in text
    assert any("Mở Shopee" in b["text"] for row in markup["inline_keyboard"] for b in row)

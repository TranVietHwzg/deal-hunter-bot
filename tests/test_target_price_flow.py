import pytest
from app.bot.telegram_service import TelegramBotService
from core import database

def test_price_parsing_helper():
    assert TelegramBotService._parse_price_from_text("100k") == 100000.0
    assert TelegramBotService._parse_price_from_text("95k") == 95000.0
    assert TelegramBotService._parse_price_from_text("95.000đ") == 95000.0
    assert TelegramBotService._parse_price_from_text("95000") == 95000.0
    assert TelegramBotService._parse_price_from_text("1.5tr") == 1500000.0
    assert TelegramBotService._parse_price_from_text("15tr") == 15000000.0
    assert TelegramBotService._parse_price_from_text("https://s.shopee.vn/4VdSGmu8Pf 100k") == 100000.0

@pytest.mark.anyio
async def test_direct_link_with_target_price():
    database.init_db()
    bot = TelegramBotService()
    
    messages = []
    photos = []
    async def mock_msg(text, reply_markup=None):
        messages.append(text)
    async def mock_photo(url, caption, reply_markup=None):
        photos.append((url, caption))
        
    bot.send_message = mock_msg
    bot.send_photo = mock_photo
    
    # 1. Gửi link kèm giá muốn đạt được: 100k
    handled = await bot.handle_direct_link("https://s.shopee.vn/4VdSGmu8Pf 100k", user_chat_id="test_user_1")
    assert handled is True
    assert len(photos) > 0 or len(messages) > 0
    
    # Kiểm tra database
    p = database.get_product_by_id("24515279749")
    assert p is not None
    assert p["target_mode"] == "PRICE"
    assert p["target_value"] == 100000.0
    assert "Yonex" in p["name"]

@pytest.mark.anyio
async def test_two_step_link_then_price_flow():
    database.init_db()
    bot = TelegramBotService()
    
    messages = []
    photos = []
    async def mock_msg(text, reply_markup=None):
        messages.append(text)
    async def mock_photo(url, caption, reply_markup=None):
        photos.append((url, caption))
        
    bot.send_message = mock_msg
    bot.send_photo = mock_photo
    
    chat_id = "test_user_flow_2"
    
    # Bước 1: Người dùng chỉ dán link trần
    await bot.handle_command("https://s.shopee.vn/4VdSGmu8Pf", user_chat_id=chat_id)
    assert chat_id in bot.pending_price_input
    assert len(photos) > 0 or len(messages) > 0
    
    # Bước 2: Người dùng nhắn giá muốn mua: 95k
    await bot.handle_command("95k", user_chat_id=chat_id)
    assert chat_id not in bot.pending_price_input
    
    # Kiểm tra sản phẩm đã lưu đúng giá 95k
    p = database.get_product_by_id("24515279749")
    assert p is not None
    assert p["target_mode"] == "PRICE"
    assert p["target_value"] == 95000.0

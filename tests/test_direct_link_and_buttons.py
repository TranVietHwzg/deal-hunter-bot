import pytest
from app.connectors.shopee_connector import ShopeeConnector
from app.bot.telegram_service import TelegramBotService

def test_parse_various_shopee_urls():
    # 1. Chuẩn dạng product/shop_id/item_id
    u1 = "https://shopee.vn/product/123456/789101112"
    p1 = ShopeeConnector.parse_shopee_url(u1)
    assert p1["shop_id"] == "123456"
    assert p1["item_id"] == "789101112"

    # 2. Dạng tên sản phẩm kèm -i.shop_id.item_id
    u2 = "https://shopee.vn/Tai-nghe-Bluetooth-Soundpeats-Air4-i.99999.87654321?sp_atk=abc"
    p2 = ShopeeConnector.parse_shopee_url(u2)
    assert p2["shop_id"] == "99999"
    assert p2["item_id"] == "87654321"

def test_main_menu_keyboard_layout():
    bot = TelegramBotService()
    kb = bot.get_main_menu_keyboard()
    assert "inline_keyboard" in kb
    rows = kb["inline_keyboard"]
    # Kiểm tra lưới 3 hàng, mỗi hàng 2 nút
    assert len(rows) == 3
    for r in rows:
        assert len(r) == 2
        for btn in r:
            assert "text" in btn
            assert "callback_data" in btn or "url" in btn

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

    # 3. Dạng username / shop_id / item_id
    u3 = "https://shopee.vn/opaanlp/1171813709/24515279749?__mobile__=1"
    p3 = ShopeeConnector.parse_shopee_url(u3)
    assert p3["shop_id"] == "1171813709"
    assert p3["item_id"] == "24515279749"

@pytest.mark.anyio
async def test_resolve_short_link_s_shopee_vn():
    # Kiểm tra giải mã link rút gọn s.shopee.vn/4VdSGmu8Pf
    res = await ShopeeConnector.resolve_url_and_parse("https://s.shopee.vn/4VdSGmu8Pf")
    assert res["item_id"] == "24515279749"
    assert res["shop_id"] == "1171813709"
    assert res["name"] is not None
    assert "Yonex" in res["name"]

def test_main_menu_keyboard_layout():
    bot = TelegramBotService()
    kb = bot.get_main_menu_keyboard()
    assert "inline_keyboard" in kb
    rows = kb["inline_keyboard"]
    # Kiểm tra lưới 2 hàng, tổng cộng 3 nút cốt lõi tối giản
    assert len(rows) == 2
    total_buttons = sum(len(r) for r in rows)
    assert total_buttons == 3
    assert rows[0][0]["callback_data"] == "action:zero_dong_active"
    assert rows[0][1]["callback_data"] == "action:zero_dong_upcoming"
    assert rows[1][0]["callback_data"] == "action:zero_dong_scan"
    for r in rows:
        for btn in r:
            assert "text" in btn
            assert "callback_data" in btn or "url" in btn

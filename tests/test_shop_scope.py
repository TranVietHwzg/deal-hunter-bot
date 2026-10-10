import pytest
from app.bot.templates import get_voucher_shop_scope, format_hot_voucher_alert, format_deal_alert, format_restock_alert
from app.bot.telegram_service import TelegramBotService
from core import database

def test_get_voucher_shop_scope():
    # 1. Shop voucher có shop_name rõ ràng
    v_shop = {
        "voucher_code": "DAREU50K",
        "voucher_type": "SHOP",
        "shop_name": "DareU Official Store",
        "category": "Voucher Shop"
    }
    assert get_voucher_shop_scope(v_shop) == "DareU Official Store"

    # 2. Toàn ngành / Toàn sàn
    v_platform = {
        "voucher_code": "SPP15MAX150K",
        "voucher_type": "PLATFORM",
        "category": "Toàn sàn"
    }
    assert get_voucher_shop_scope(v_platform) is None

    # 3. Ngành hàng / Live / Video (toàn ngành)
    v_live = {
        "voucher_code": "VIDEO20K",
        "voucher_type": "LIVE_VIDEO",
        "category": "Shopee Video"
    }
    assert get_voucher_shop_scope(v_live) is None

    # 4. Shop voucher nhưng không có shop_name mà chỉ có shop_id
    v_shop_id = {
        "voucher_code": "SHOP123",
        "voucher_type": "SHOP",
        "shop_id": "12345",
        "category": "Voucher Shop"
    }
    assert get_voucher_shop_scope(v_shop_id) == "Shop ID 12345"

def test_format_hot_voucher_alert_with_and_without_shop():
    v_shop = {
        "voucher_code": "YONEX50K",
        "voucher_type": "SHOP",
        "shop_name": "Yonex Official Store",
        "category": "Voucher Shop",
        "discount_type": "FIXED_AMOUNT",
        "discount_value": 50000,
        "min_spend": 300000,
        "platform_id": "SHOPEE"
    }
    msg_shop = format_hot_voucher_alert(v_shop)
    assert "🏪 <b>Áp dụng:</b> Chỉ Shop Yonex Official Store" in msg_shop

    v_all = {
        "voucher_code": "SALE15PCT",
        "voucher_type": "PLATFORM",
        "category": "Toàn sàn",
        "discount_type": "PERCENTAGE",
        "discount_value": 15,
        "max_discount_amount": 150000,
        "min_spend": 400000,
        "platform_id": "SHOPEE"
    }
    msg_all = format_hot_voucher_alert(v_all)
    # Không được ghi thông tin shop nếu là toàn ngành / toàn sàn
    assert "Áp dụng: Chỉ Shop" not in msg_all
    assert "Toàn sàn" in msg_all

@pytest.mark.anyio
async def test_add_voucher_command():
    bot = TelegramBotService()
    async def mock_msg(text, reply_markup=None):
        return {"ok": True}
    bot.send_message = mock_msg
    
    # 1. Thêm voucher cho shop cụ thể
    await bot._cmd_add_voucher(["TESTSHOP30", "30k", "200k", "Anker", "Official"])
    saved_shop = database.get_voucher_by_id("TESTSHOP30")
    assert saved_shop is not None
    assert saved_shop["voucher_type"] == "SHOP"
    assert saved_shop["shop_name"] == "Anker Official"
    assert saved_shop["discount_value"] == 30000.0
    assert saved_shop["min_spend"] == 200000.0

    # 2. Thêm voucher toàn ngành / toàn sàn
    await bot._cmd_add_voucher(["TESTALL50", "50k", "300k"])
    saved_all = database.get_voucher_by_id("TESTALL50")
    assert saved_all is not None
    assert saved_all["voucher_type"] == "PLATFORM"
    assert saved_all["shop_name"] in [None, ""]
    assert saved_all["discount_value"] == 50000.0

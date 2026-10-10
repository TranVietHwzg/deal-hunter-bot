import asyncio
import json
import os
import sys

# Cấu hình UTF-8 cho Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
import uvicorn
from core import database, scanner
from bot.telegram_bot import TelegramDealBot
from web.app import app

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

async def seed_demo_data_if_empty():
    """Tạo sẵn 1 vài deal mẫu chất lượng để giao diện trực quan ngay khi mở"""
    products = database.get_all_products()
    if not products:
        database.add_product(
            item_id="12345678",
            shop_id="88888",
            name="Bàn phím cơ không dây DareU EK87 White LED (Chính Hãng)",
            url="https://shopee.vn",
            image_url="https://down-vn.img.susercontent.com/file/vn-11134207-7r98o-ls85u3q3v9c22e",
            target_mode="PERCENT",
            target_value=30.0,
            baseline_price=650000
        )
        database.add_product(
            item_id="87654321",
            shop_id="99999",
            name="Tai nghe Bluetooth Soundpeats Air4 Lite Chống Ồn AI",
            url="https://shopee.vn",
            image_url="https://down-vn.img.susercontent.com/file/vn-11134207-7r98o-ls2m2155b4m552",
            target_mode="PERCENT",
            target_value=35.0,
            baseline_price=950000
        )
        print("[Init] Đã nạp sẵn 2 sản phẩm mẫu vào Watchlist.")

async def main():
    print("==================================================================")
    print("🚀 KHỞI ĐỘNG HỆ THỐNG BOT SĂN DEAL & VOUCHER CÁ NHÂN (DEAL HUNTER)")
    print("==================================================================")
    
    config = load_config()
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or config.get("telegram", {}).get("bot_token")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.get("telegram", {}).get("chat_id")
    port = int(os.environ.get("PORT") or config.get("settings", {}).get("web_port", 8000))

    # 1. Khởi tạo DB & Dữ liệu
    database.init_db()
    await scanner.seed_default_vouchers()
    await seed_demo_data_if_empty()

    # 2. Khởi tạo Telegram Bot
    bot_instance = TelegramDealBot(token, chat_id)

    # 3. Chạy 1 chu kỳ đối soát đầu tiên
    await scanner.run_scan_cycle(bot_instance)

    # 4. Cấu hình Uvicorn Web Server (host 0.0.0.0 để Render mở cổng ra internet)
    web_config = uvicorn.Config(app=app, host="0.0.0.0", port=port, log_level="warning")
    web_server = uvicorn.Server(web_config)

    print(f"\n🌐 Giao diện Web Dashboard đã sẵn sàng tại: http://localhost:{port}")
    print(f"🤖 Bot Telegram @San_deal_Huvg_bot đã sẵn sàng nhận lệnh từ bạn.\n")

    # 5. Chạy song song cả 3 luồng: Web Server, Bot Polling, Background Scanner
    await asyncio.gather(
        web_server.serve(),
        bot_instance.start_polling(),
        scanner.background_scanner_loop(bot_instance, config)
    )

if __name__ == "__main__":
    asyncio.run(main())

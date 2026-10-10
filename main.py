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
from app.bot.telegram_service import TelegramBotService
from web.app import app

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

async def main():
    print("==================================================================")
    print("📡 KHỞI ĐỘNG SHOPEE UPCOMING HIDDEN VOUCHER RADAR (PRODUCTION)")
    print("==================================================================")
    
    config = load_config()
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or config.get("telegram", {}).get("bot_token")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or config.get("telegram", {}).get("chat_id")
    port = int(os.environ.get("PORT") or config.get("settings", {}).get("web_port", 8000))

    # 1. Khởi tạo Cơ sở dữ liệu SQLite & Migration
    database.init_db()

    # 2. Khởi tạo Telegram Bot Service
    bot_instance = TelegramBotService(token=token, chat_id=chat_id)

    # 3. Nạp và quét chu kỳ khởi động ban đầu
    print("\n• Đang kiểm tra các chiến dịch và mã Shopee công khai ban đầu...")
    await scanner.seed_default_vouchers()
    await scanner.run_radar_cycle(bot_instance)

    # 4. Cấu hình Uvicorn Web Server cho Render (host 0.0.0.0, port lấy từ $PORT)
    web_config = uvicorn.Config(app=app, host="0.0.0.0", port=port, log_level="warning")
    web_server = uvicorn.Server(web_config)

    print(f"\n🌐 Web Server & Healthcheck Render đã lắng nghe tại: http://0.0.0.0:{port}")
    print(f"🤖 Telegram Radar @San_deal_Huvg_bot đã sẵn sàng hoạt động.")
    print("• Tính năng: Radar mã sắp mở, mã ẩn công khai, voucher shop, zero freeship.")
    print("• Tự động thích ứng tần suất theo khung giờ khuyến mãi.\n")

    # 5. Chạy song song cả 3 luồng: Web Server (cho Render Port Binding), Bot Polling, Background Scheduler
    await asyncio.gather(
        web_server.serve(),
        bot_instance.start_polling(),
        scanner.background_radar_loop(bot_instance)
    )

if __name__ == "__main__":
    asyncio.run(main())

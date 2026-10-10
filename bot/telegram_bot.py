import asyncio
from app.bot.telegram_service import TelegramBotService

class TelegramDealBot(TelegramBotService):
    """
    Kế thừa hoàn toàn từ TelegramBotService chuẩn Production.
    Tự động bắt link dán trực tiếp, cảnh báo voucher chủ động,
    nút bấm xếp lưới 2-3 cột gọn gàng và đẹp mắt.
    """
    def __init__(self, token: str, chat_id: str):
        super().__init__(token=token, chat_id=chat_id)

import asyncio
from app.bot.telegram_service import TelegramBotService

class TelegramDealBot(TelegramBotService):
    """
    Kế thừa hoàn toàn từ TelegramBotService chuẩn Production,
    bổ sung các hàm tương thích ngược với hệ thống cũ.
    """
    def __init__(self, token: str, chat_id: str):
        super().__init__(token=token, chat_id=chat_id)

    async def send_deal_alert(self, product, evaluation, alert_reason="DEAL_MOI"):
        """Gửi thông báo khi một món hàng đạt mục tiêu giảm giá sau khi gộp mã"""
        tier = evaluation.get("tier_label", "🔥 DEAL HOT")
        prefix = "🚨 [GIÁ MỚI TỐT HƠN]" if alert_reason == "GIA_TOT_HON" else tier

        vouchers_text = ""
        for v in evaluation.get("applied_vouchers", []):
            vouchers_text += f"  • <b>{v.get('type')}</b>: {v.get('label') or v.get('title')}\n"

        if not vouchers_text:
            vouchers_text = "  • <i>(Không cần mã, shop đang giảm trực tiếp)</i>\n"

        target_str = f"≥ {product.get('target_value')}%" if product.get('target_mode') == 'PERCENT' else f"≤ {int(product.get('target_value', 0)):,}đ"

        msg = (
            f"<b>{prefix}</b>\n\n"
            f"📦 <b>Sản phẩm:</b> {product.get('name')}\n"
            f"📊 <b>Giá niêm yết:</b> <s>{int(evaluation.get('baseline_price', 0)):,}đ</s>\n"
            f"💥 <b>GIÁ THỰC TRẢ SAU MÃ:</b> <b><u>{int(evaluation.get('final_price', 0)):,}đ</u></b>\n"
            f"📉 <b>Mức giảm thật:</b> <b>-{evaluation.get('discount_percent')}%</b> (Tiết kiệm {int(evaluation.get('savings', 0)):,}đ)\n"
            f"🎯 <b>Mục tiêu của bạn:</b> {target_str}\n\n"
            f"🎫 <b>CÁC VOUCHER ĐANG ÁP DỤNG:</b>\n"
            f"{vouchers_text}\n"
            f"⚠️ <i>Lưu ý: Vào Shopee kiểm tra lưu các mã trên rồi đặt mua thủ công để đảm bảo an toàn.</i>"
        )

        buttons = {
            "inline_keyboard": [
                [{"text": "🛒 BẤM MUA NGAY TRÊN SHOPEE", "url": product.get('product_url', 'https://shopee.vn')}],
                [{"text": "📋 Xem Watchlist", "callback_data": "menu_list"}, {"text": "⚡️ Quét Ngay", "callback_data": "menu_check"}]
            ]
        }

        img = product.get("image_url") or "https://deo.shopeemobile.com/shopee/shopee-pcmall-live-sg/assets/icon_favicon_1_32.png"
        await self.send_photo(img, msg, reply_markup=buttons)

    def get_main_menu_keyboard(self):
        return {
            "inline_keyboard": [
                [
                    {"text": "📋 Xem Danh Sách Canh", "callback_data": "menu_list"},
                    {"text": "➕ Thêm Sản Phẩm", "callback_data": "menu_add_guide"}
                ],
                [
                    {"text": "⚡️ Quét Deal Ngay", "callback_data": "menu_check"},
                    {"text": "🎫 Kho Voucher Xịn", "callback_data": "menu_vouchers"}
                ]
            ]
        }

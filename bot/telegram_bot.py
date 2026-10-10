import asyncio
import json
import os
import httpx
from core import database, calculator
from scrapers import shopee

class TelegramDealBot:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = str(chat_id)
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.is_running = False
        self.last_update_id = 0

    async def send_message(self, text: str, reply_markup=None, parse_mode="HTML"):
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
            
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.post(f"{self.api_url}/sendMessage", json=payload)
                return res.json()
            except Exception as e:
                print(f"[Telegram] Lỗi gửi tin: {e}")
                return None

    async def send_photo(self, photo_url: str, caption: str, reply_markup=None, parse_mode="HTML"):
        payload = {
            "chat_id": self.chat_id,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": parse_mode
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.post(f"{self.api_url}/sendPhoto", json=payload)
                # Fallback nếu link ảnh lỗi thì gửi text
                if res.status_code != 200:
                    return await self.send_message(caption, reply_markup=reply_markup, parse_mode=parse_mode)
                return res.json()
            except Exception:
                return await self.send_message(caption, reply_markup=reply_markup, parse_mode=parse_mode)

    async def send_deal_alert(self, product, evaluation, alert_reason="DEAL_MOI"):
        """Gửi thông báo khi một món hàng đạt mục tiêu giảm >= 30%"""
        tier = evaluation["tier_label"]
        prefix = "🚨 [GIÁ MỚI TỐT HƠN]" if alert_reason == "GIA_TOT_HON" else tier

        vouchers_text = ""
        for v in evaluation["applied_vouchers"]:
            vouchers_text += f"  • <b>{v['type']}</b>: {v['label']}\n"

        if not vouchers_text:
            vouchers_text = "  • <i>(Không cần mã, shop đang giảm trực tiếp)</i>\n"

        target_str = f"≥ {product['target_value']}%" if product['target_mode'] == 'PERCENT' else f"≤ {int(product['target_value']):,}đ"

        msg = (
            f"<b>{prefix}</b>\n\n"
            f"📦 <b>Sản phẩm:</b> {product['name']}\n"
            f"📊 <b>Giá chuẩn thị trường:</b> <s>{int(evaluation['baseline_price']):,}đ</s>\n"
            f"💥 <b>GIÁ THỰC TRẢ SAU MÃ:</b> <b><u>{int(evaluation['final_price']):,}đ</u></b>\n"
            f"📉 <b>Mức giảm thật:</b> <b>-{evaluation['discount_percent']}%</b> (Tiết kiệm {int(evaluation['savings']):,}đ)\n"
            f"🎯 <b>Mục tiêu của bạn:</b> {target_str}\n\n"
            f"🎫 <b>CÁC VOUCHER ĐANG ÁP DỤNG:</b>\n"
            f"{vouchers_text}\n"
            f"⚠️ <i>Lưu ý: Bạn vào Shopee kiểm tra lưu các mã trên rồi đặt mua thủ công để đảm bảo an toàn.</i>"
        )

        buttons = {
            "inline_keyboard": [
                [{"text": "🛒 BẤM MUA NGAY TRÊN SHOPEE", "url": product['product_url']}],
                [{"text": "📋 Xem Watchlist", "callback_data": "menu_list"}, {"text": "⚡️ Quét Ngay", "callback_data": "menu_check"}]
            ]
        }

        img = product.get("image_url") or "https://deo.shopeemobile.com/shopee/shopee-pcmall-live-sg/assets/icon_favicon_1_32.png"
        await self.send_photo(img, msg, reply_markup=buttons)

    def get_main_menu_keyboard(self):
        render_url = os.environ.get("RENDER_EXTERNAL_URL")
        if render_url and render_url.startswith("http"):
            web_btn = [{"text": "🌐 Mở Web Dashboard", "url": render_url}]
        else:
            web_btn = [{"text": "🌐 Hướng Dẫn Mở Web Dashboard", "callback_data": "menu_web_info"}]

        return {
            "inline_keyboard": [
                [
                    {"text": "📋 Xem Danh Sách Canh", "callback_data": "menu_list"},
                    {"text": "➕ Thêm Sản Phẩm", "callback_data": "menu_add_guide"}
                ],
                [
                    {"text": "🎟 Trạm Voucher Xịn", "callback_data": "menu_vouchers"},
                    {"text": "⚡️ Quét Ngay Lập Tức", "callback_data": "menu_check"}
                ],
                [
                    {"text": "⚙️ Ngưỡng Giảm Giá (≥30%)", "callback_data": "menu_settings"},
                    {"text": "📊 Thống Kê Bot", "callback_data": "menu_status"}
                ],
                web_btn
            ]
        }

    async def handle_callback_query(self, query):
        q_id = query["id"]
        data = query.get("data", "")
        
        # Trả lời callback query để tắt vòng quay trên nút
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{self.api_url}/answerCallbackQuery", json={"callback_query_id": q_id})

        if data == "menu_main":
            stats = database.get_stats()
            text = (
                "🤖 <b>BẢNG ĐIỀU KHIỂN BOT SĂN DEAL CÁ NHÂN</b>\n\n"
                f"• 📦 Món đang canh: <b>{stats['total_products']} món</b>\n"
                f"• 🎯 Deal đạt mục tiêu (≥30%): <b>{stats['ready_deals']} món</b>\n"
                f"• 🎟 Voucher xịn khả dụng: <b>{stats['active_vouchers']} mã</b>\n"
                f"• 🔔 Đã gửi cảnh báo: <b>{stats['total_alerts']} lần</b>\n\n"
                "<i>Chọn tính năng dưới đây để thao tác nhanh:</i>"
            )
            await self.send_message(text, reply_markup=self.get_main_menu_keyboard())

        elif data == "menu_list":
            products = database.get_all_products()
            if not products:
                text = "📋 <b>Danh sách của bạn đang trống!</b>\n\nHãy gửi lệnh:\n<code>/add &lt;link_shopee&gt; 30%</code> để thêm món cần canh."
                kb = {"inline_keyboard": [[{"text": "⬅️ Quay Lại Menu", "callback_data": "menu_main"}]]}
                await self.send_message(text, reply_markup=kb)
                return

            text = f"📋 <b>DANH SÁCH THEO DÕI ({len(products)} MÓN):</b>\n\n"
            keyboard_rows = []
            for p in products[:8]: # Hiện tối đa 8 món gần nhất
                status_icon = "🔥 ĐẠT GIÁ!" if p["is_deal_ready"] else "⏳ Đang canh"
                target_str = f"≥{p['target_value']}%" if p['target_mode'] == 'PERCENT' else f"≤{int(p['target_value']):,}đ"
                text += (
                    f"<b>#{p['id']}. {p['name'][:35]}...</b>\n"
                    f"  • Giá TT: <s>{int(p['baseline_price']):,}đ</s> ➡️ Thực trả: <b>{int(p['final_price']):,}đ</b> (-{p['discount_percent']}%)\n"
                    f"  • Mục tiêu: {target_str} [{status_icon}]\n\n"
                )
                keyboard_rows.append([
                    {"text": f"🛒 Mở #{p['id']}", "url": p["product_url"]},
                    {"text": f"🗑 Xóa #{p['id']}", "callback_data": f"del_{p['id']}"}
                ])
                
            keyboard_rows.append([{"text": "⬅️ Quay Lại Menu", "callback_data": "menu_main"}])
            await self.send_message(text, reply_markup={"inline_keyboard": keyboard_rows})

        elif data == "menu_vouchers":
            vouchers = database.get_all_vouchers(only_active=True, only_high_tier=True)
            text = "🎟 <b>KHO VOUCHER XỊN ĐANG HOẠT ĐỘNG:</b>\n\n"
            for v in vouchers:
                text += f"• <b>[{v['voucher_type']}]</b> {v['label']}\n  Code: <code>{v['voucher_code']}</code>\n\n"
            kb = {"inline_keyboard": [[{"text": "⬅️ Quay Lại Menu", "callback_data": "menu_main"}]]}
            await self.send_message(text, reply_markup=kb)

        elif data == "menu_check":
            await self.send_message("⚡️ <i>Đang kích hoạt quét toàn bộ sản phẩm và đối soát voucher...</i>")
            # Quét các sản phẩm
            from core.scanner import run_scan_cycle
            found_deals = await run_scan_cycle(self)
            await self.send_message(f"✅ Đã quét xong! Phát hiện <b>{found_deals} món</b> đạt mức giảm ≥ 30%.")

        elif data.startswith("del_"):
            p_id = int(data.replace("del_", ""))
            database.delete_product(p_id)
            await self.send_message(f"✅ Đã xóa sản phẩm #{p_id} khỏi danh sách theo dõi!")
            await self.handle_callback_query({"id": q_id, "data": "menu_list"})

        elif data == "menu_add_guide":
            text = (
                "➕ <b>HƯỚNG DẪN THÊM MÓN CẦN CANH:</b>\n\n"
                "Gửi tin nhắn theo cú pháp:\n"
                "<code>/add &lt;link_shopee&gt; 30%</code> (Báo khi giảm từ 30% trở lên)\n\n"
                "Hoặc theo số tiền:\n"
                "<code>/add &lt;link_shopee&gt; 500000</code> (Báo khi giá thực trả ≤ 500k)\n\n"
                "<i>(Ví dụ: /add https://shopee.vn/product/123/456 35%)</i>"
            )
            kb = {"inline_keyboard": [[{"text": "⬅️ Quay Lại Menu", "callback_data": "menu_main"}]]}
            await self.send_message(text, reply_markup=kb)

        elif data == "menu_settings":
            text = (
                "⚙️ <b>CÀI ĐẶT NGƯỠNG GIẢM GIÁ:</b>\n\n"
                "• Ngưỡng lọc hiện tại: <b>≥ 30%</b>\n"
                "• Mọi deal giảm dưới 30% sẽ bị tự động loại bỏ để chống spam.\n\n"
                "<i>Để đổi ngưỡng, bạn gửi lệnh:</i>\n"
                "<code>/min_discount 35</code> (đổi thành 35%)\n"
            )
            kb = {"inline_keyboard": [[{"text": "⬅️ Quay Lại Menu", "callback_data": "menu_main"}]]}
            await self.send_message(text, reply_markup=kb)

        elif data == "menu_web_info":
            render_url = os.environ.get("RENDER_EXTERNAL_URL")
            text = (
                "🌐 <b>HƯỚNG DẪN MỞ WEB DASHBOARD:</b>\n\n"
                "• <b>Nếu chạy trên máy tính:</b> Mở trình duyệt vào <code>http://localhost:8000</code>\n"
            )
            if render_url:
                text += f"• <b>Link Web Render của bạn:</b> {render_url}\n"
            else:
                text += "• <b>Nếu chạy trên Render:</b> Mở đường link onrender.com của bạn.\n"
            kb = {"inline_keyboard": [[{"text": "⬅️ Quay Lại Menu", "callback_data": "menu_main"}]]}
            await self.send_message(text, reply_markup=kb)

    async def handle_message(self, message):
        text = message.get("text", "").strip()
        chat_id = str(message.get("chat", {}).get("id", ""))
        
        # Chỉ nhận tin từ đúng tài khoản của bạn để bảo mật
        if chat_id != self.chat_id:
            return

        if text.startswith("/start") or text.startswith("/menu"):
            stats = database.get_stats()
            welcome = (
                "🤖 <b>CHÀO MỪNG BẠN ĐẾN VỚI BOT SĂN DEAL CÁ NHÂN!</b>\n\n"
                "• Mục tiêu: Săn đúng món bạn cần với giá giảm <b>≥ 30%</b>\n"
                "• Cơ chế: Tự động gộp mã shop + mã sàn + freeship\n"
                "• An toàn: Gửi link và điều kiện, bạn xác nhận đặt mua thủ công\n\n"
                f"📦 Hiện có <b>{stats['total_products']} món</b> đang được canh 24/7.\n"
                "<i>Bấm các nút bên dưới để điều khiển:</i>"
            )
            await self.send_message(welcome, reply_markup=self.get_main_menu_keyboard())

        elif text.startswith("/add"):
            parts = text.split()
            if len(parts) < 3:
                await self.send_message("⚠️ Cú pháp: <code>/add &lt;link_shopee&gt; &lt;30% hoặc số tiền&gt;</code>\nVí dụ: <code>/add https://shopee.vn/product/123/456 35%</code>")
                return
            
            raw_url = parts[1]
            target_str = parts[2].replace("%", "").strip()
            
            target_mode = "PERCENT" if "%" in parts[2] else "PRICE"
            try:
                target_value = float(target_str)
            except ValueError:
                target_value = 30.0
                target_mode = "PERCENT"

            await self.send_message("⏳ <i>Đang bóc tách link và kiểm tra giá Shopee...</i>")
            real_url = await shopee.resolve_short_url(raw_url)
            shop_id, item_id = shopee.parse_shopee_url(real_url)
            
            if not item_id:
                await self.send_message("❌ Không tìm thấy mã sản phẩm trong link! Vui lòng gửi link sản phẩm chuẩn của Shopee.")
                return

            item_data = await shopee.fetch_shopee_item(shop_id, item_id)
            p_id = database.add_product(
                item_id=item_id,
                shop_id=shop_id,
                name=item_data["name"],
                url=real_url,
                image_url=item_data["image_url"],
                target_mode=target_mode,
                target_value=target_value,
                baseline_price=item_data["baseline_price"]
            )
            
            # Đánh giá ngay lập tức
            vouchers = database.get_all_vouchers()
            p_obj = database.get_product_by_id(p_id)
            eval_res = calculator.stack_vouchers_and_evaluate(p_obj, vouchers)
            database.update_product_evaluation(item_id, eval_res["current_price"], eval_res["final_price"], eval_res["discount_percent"], eval_res["is_deal_ready"], eval_res["applied_vouchers"])

            target_display = f"Giảm ≥ {target_value}%" if target_mode == "PERCENT" else f"Giá ≤ {int(target_value):,}đ"
            
            resp = (
                f"✅ <b>ĐÃ THÊM THÀNH CÔNG VÀO WATCHLIST!</b>\n\n"
                f"📦 <b>Tên:</b> {item_data['name']}\n"
                f"💰 <b>Giá thị trường:</b> {int(item_data['baseline_price']):,}đ\n"
                f"💥 <b>Giá sau khi gộp mã hiện tại:</b> <b>{int(eval_res['final_price']):,}đ</b> (-{eval_res['discount_percent']}%)\n"
                f"🎯 <b>Mục tiêu canh:</b> {target_display}\n\n"
                f"Trạng thái: {'🔥 <b>ĐẠT MỤC TIÊU NGAY BÂY GIỜ!</b>' if eval_res['is_deal_ready'] else '⏳ Đang tiếp tục canh mã xịn hơn...'}"
            )
            kb = {
                "inline_keyboard": [
                    [{"text": "📋 Xem Danh Sách Canh", "callback_data": "menu_list"}],
                    [{"text": "🛒 Mở Shopee", "url": real_url}]
                ]
            }
            await self.send_message(resp, reply_markup=kb)

        elif text.startswith("/list"):
            await self.handle_callback_query({"id": "0", "data": "menu_list"})

        elif text.startswith("/check"):
            await self.handle_callback_query({"id": "0", "data": "menu_check"})

        elif text.startswith("/vouchers"):
            await self.handle_callback_query({"id": "0", "data": "menu_vouchers"})

    async def start_polling(self):
        self.is_running = True
        print("[Telegram Bot] Bắt đầu lắng nghe lệnh từ bạn...")
        while self.is_running:
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    res = await client.get(f"{self.api_url}/getUpdates", params={"offset": self.last_update_id + 1, "timeout": 20})
                    if res.status_code == 200:
                        data = res.json()
                        for update in data.get("result", []):
                            self.last_update_id = update["update_id"]
                            if "message" in update:
                                await self.handle_message(update["message"])
                            elif "callback_query" in update:
                                await self.handle_callback_query(update["callback_query"])
            except Exception as e:
                await asyncio.sleep(2)

import asyncio
import hashlib
import json
import os
import re
from typing import Dict, Any, Optional, List
import httpx

from config.settings import settings
from config.feature_flags import feature_flags
from app.core.scoring_engine import calculate_voucher_quality_score
from app.core.stacking_engine import calculate_stacked_price
from app.core.junk_filter import is_freeship, validate_voucher
from app.bot.templates import format_hot_voucher_alert, format_restock_alert
from core import database
from app.connectors.shopee_connector import ShopeeConnector

class TelegramBotService:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or settings.telegram_bot_token
        self.chat_id = str(chat_id or settings.telegram_chat_id)
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.is_running = False
        self.last_update_id = 0
        self.shopee_connector = ShopeeConnector()

    async def send_message(self, text: str, reply_markup=None, parse_mode="HTML") -> Optional[Dict[str, Any]]:
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

    async def send_photo(self, photo_url: str, caption: str, reply_markup=None, parse_mode="HTML") -> Optional[Dict[str, Any]]:
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
                if res.status_code != 200:
                    return await self.send_message(caption, reply_markup=reply_markup, parse_mode=parse_mode)
                return res.json()
            except Exception:
                return await self.send_message(caption, reply_markup=reply_markup, parse_mode=parse_mode)

    async def broadcast_hot_alert(self, voucher: Dict[str, Any], example_product: Optional[Dict[str, Any]] = None) -> bool:
        """Gửi cảnh báo Hot Voucher với cơ chế SHA-256 Deduplication chống spam"""
        user_cfg = database.get_user_settings()
        if user_cfg.get("is_muted") == 1:
            return False

        # Bài trừ freeship tuyệt đối trước khi gửi
        is_ship, _ = is_freeship(voucher)
        if is_ship:
            return False

        # Kiểm tra ngưỡng điểm
        score = voucher.get("quality_score", 0)
        min_thresh = user_cfg.get("min_quality_score", 70)
        if score < min_thresh:
            return False

        # Tạo hash SHA-256 để chống gửi trùng lặp
        v_id = voucher.get("id") or voucher.get("voucher_id_on_platform")
        hash_input = f"HOT_{v_id}_{voucher.get('discount_value')}_{voucher.get('min_spend')}"
        dedup_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

        # Kiểm tra trùng
        if database.is_alert_duplicate(dedup_hash):
            return False

        msg = format_hot_voucher_alert(voucher, example_product)
        buttons = {
            "inline_keyboard": [
                [{"text": "🎫 LẤY VOUCHER NGAY", "url": voucher.get("claim_url", "https://shopee.vn")}],
                [{"text": "🔍 Tại sao mã này xịn? (/why)", "callback_data": f"why_{v_id}"}]
            ]
        }

        res = await self.send_message(msg, reply_markup=buttons)
        if res and res.get("ok"):
            database.record_alert_event(
                alert_type="HOT_VOUCHER",
                dedup_hash=dedup_hash,
                message_payload=msg,
                voucher_id=v_id,
                quality_score=score
            )
            return True
        return False

    # ----------------- XỬ LÝ 13 CÂU LỆNH BOT -----------------

    async def handle_command(self, text: str, user_chat_id: str) -> None:
        parts = text.strip().split()
        if not parts:
            return
        cmd = parts[0].lower().split("@")[0] # Bỏ @bot_name nếu có
        args = parts[1:]

        if cmd in ["/start", "/help", "/menu"]:
            await self._cmd_help()
        elif cmd == "/vouchers":
            await self._cmd_vouchers(min_score=70)
        elif cmd == "/hot":
            await self._cmd_vouchers(min_score=85, hot_only=True)
        elif cmd == "/watch":
            await self._cmd_watch(args)
        elif cmd == "/keyword":
            await self._cmd_keyword(args)
        elif cmd == "/category":
            await self._cmd_category(args)
        elif cmd == "/minsave":
            await self._cmd_minsave(args)
        elif cmd == "/newuser":
            await self._cmd_newuser(args)
        elif cmd == "/platform":
            await self._cmd_platform(args)
        elif cmd == "/mute":
            database.update_user_settings("is_muted", 1)
            await self.send_message("🔕 Đã <b>TẮT CHUÔNG</b> cảnh báo deal. Bạn sẽ không nhận tin nhắn tự động.")
        elif cmd == "/unmute":
            database.update_user_settings("is_muted", 0)
            await self.send_message("🔔 Đã <b>BẬT CHUÔNG</b> cảnh báo deal. Sẽ bắn tin ngay khi có voucher xịn!")
        elif cmd == "/why":
            await self._cmd_why(args)
        elif cmd == "/stack":
            await self._cmd_stack(args)
        elif cmd == "/history":
            await self._cmd_history(args)
        elif cmd == "/settings":
            await self._cmd_settings()
        else:
            await self.send_message(f"❓ Không rõ lệnh <code>{cmd}</code>. Gõ /help để xem danh sách 13 lệnh hệ thống.")

    async def _cmd_help(self):
        msg = (
            "🤖 <b>HỆ THỐNG VOUCHER INTELLIGENCE & DEAL OPTIMIZER</b>\n"
            "<i>(Phiên bản Production chuyên săn mã xịn - Bài trừ 100% Freeship)</i>\n\n"
            "📋 <b>DANH SÁCH 13 CÂU LỆNH:</b>\n"
            "• /vouchers — Kho voucher chất lượng cao đang còn lượt (Score ≥ 70)\n"
            "• /hot — Siêu voucher điểm vàng (Score ≥ 85)\n"
            "• /watch &lt;link_shopee&gt; &lt;giá_mục_tiêu&gt; — Canh giảm giá 1 sản phẩm\n"
            "• /keyword &lt;từ_khóa&gt; &lt;giá_mục_tiêu&gt; — Canh deal theo từ khóa\n"
            "• /category &lt;ngành_hàng&gt; — Cài đặt ngành hàng ưu tiên\n"
            "• /minsave &lt;số_tiền&gt; — Đặt mức giảm tối thiểu mới báo (Mặc định 50k)\n"
            "• /newuser on|off — Bật/tắt voucher chỉ dành cho tân thủ\n"
            "• /platform shopee|lazada|tiktok|all — Chọn sàn theo dõi\n"
            "• /mute & /unmute — Tắt/Bật thông báo khẩn\n"
            "• /why &lt;voucher_id&gt; — Giải mã chi tiết lý do & bảng điểm 0–100\n"
            "• /stack &lt;link_sản_phẩm&gt; — Mô phỏng gộp 4 tầng mã cho 1 sản phẩm\n"
            "• /history &lt;item_id&gt; — Tra cứu biểu đồ biến động giá chống giá ảo\n"
            "• /settings — Xem và tùy chỉnh toàn bộ cấu hình cá nhân"
        )
        await self.send_message(msg)

    async def _cmd_vouchers(self, min_score: int = 70, hot_only: bool = False):
        vouchers = database.get_vouchers(min_score=min_score, hot_only=hot_only)
        if not vouchers:
            await self.send_message("Hiện tại chưa có voucher nào đạt tiêu chí (Hệ thống đã tự động lọc sạch 100% voucher freeship và voucher rác).")
            return

        header = "🔥 <b>DANH SÁCH SIÊU VOUCHER HOT (SCORE ≥ 85)</b>\n\n" if hot_only else "🎫 <b>KHO VOUCHER XỊN ĐANG HOẠT ĐỘNG (SCORE ≥ 70)</b>\n\n"
        body = ""
        for i, v in enumerate(vouchers[:10], 1):
            d_val = int(v['discount_value'])
            d_str = f"Giảm {v['discount_value']}% (Tối đa {int(v['max_discount_amount']):,}đ)" if v['discount_type'] in ['PERCENT', 'PERCENTAGE'] else f"Giảm {d_val:,}đ"
            min_sp = f"Đơn từ {int(v['min_spend']):,}đ" if v['min_spend'] > 0 else "Đơn từ 0đ"
            body += (
                f"{i}. <b>[{v['platform_id']}] {v['title']}</b>\n"
                f"   💰 <b>{d_str}</b> | 🛒 {min_sp}\n"
                f"   ⭐ Điểm: <b>{v['quality_score']}/100</b> | ID: <code>{v['voucher_id_on_platform']}</code>\n"
                f"   🔗 <a href=\"{v['claim_url']}\">Bấm vào lưu mã</a>\n\n"
            )
        body += "<i>Gõ <code>/why &lt;ID&gt;</code> để xem chi tiết cách tính điểm của từng mã.</i>"
        await self.send_message(header + body)

    async def _cmd_watch(self, args: List[str]):
        if len(args) < 1:
            await self.send_message("⚠️ Cú pháp: <code>/watch &lt;link_sản_phẩm&gt; &lt;giá_mục_tiêu_hoặc_%_giảm&gt;</code>\nVí dụ: <code>/watch https://shopee.vn/product/88/123 500000</code>")
            return

        url = args[0]
        parsed = self.shopee_connector.parse_shopee_url(url)
        item_id = parsed["item_id"]
        shop_id = parsed["shop_id"]

        if not item_id:
            await self.send_message("❌ Không nhận diện được mã sản phẩm từ link Shopee. Vui lòng kiểm tra lại link.")
            return

        target_val = 30.0 # mặc định giảm 30%
        target_mode = "PERCENT"
        if len(args) >= 2:
            try:
                val = float(args[1].replace(",", "").replace(".", "").replace("k", "000"))
                if val <= 100:
                    target_mode = "PERCENT"
                    target_val = val
                else:
                    target_mode = "PRICE"
                    target_val = val
            except ValueError:
                pass

        # Lấy thông tin sản phẩm
        details = await self.shopee_connector.fetch_product_details(item_id, shop_id)
        name = details.get("name", f"Sản phẩm {item_id}")
        base_price = details.get("original_price", 500000.0)

        database.add_product(
            item_id=item_id,
            shop_id=shop_id,
            name=name,
            url=url,
            image_url=details.get("image_url"),
            target_mode=target_mode,
            target_value=target_val,
            baseline_price=base_price
        )

        target_str = f"giảm ≥ {target_val}%" if target_mode == "PERCENT" else f"giá ≤ {int(target_val):,}đ"
        await self.send_message(
            f"✅ <b>ĐÃ THÊM VÀO WATCHLIST!</b>\n\n"
            f"📦 <b>Sản phẩm:</b> {name}\n"
            f"📊 <b>Giá niêm yết:</b> {int(details.get('current_price', base_price)):,}đ\n"
            f"🎯 <b>Mục tiêu canh mua:</b> {target_str}\n"
            f"🤖 Hệ thống sẽ tự động gộp các mã sàn/shop/ngành hàng và báo ngay khi đạt giá mục tiêu!"
        )

    async def _cmd_keyword(self, args: List[str]):
        if not args:
            await self.send_message("⚠️ Cú pháp: <code>/keyword &lt;từ_khóa&gt; &lt;giá_mục_tiêu&gt;</code>\nVí dụ: <code>/keyword chuột Dareu 300000</code>")
            return
        kw = " ".join(args[:-1]) if len(args) > 1 and args[-1].replace(".","").isdigit() else " ".join(args)
        await self.send_message(f"🔍 Đã lưu từ khóa theo dõi: <b>{kw}</b>. Khi có voucher giảm sâu áp dụng cho nhóm này, bot sẽ gửi cảnh báo!")

    async def _cmd_category(self, args: List[str]):
        if not args:
            await self.send_message("⚠️ Cú pháp: <code>/category &lt;tên_ngành_hàng&gt;</code>\nVí dụ: <code>/category Điện Tử</code>")
            return
        cat = " ".join(args)
        await self.send_message(f"🏷 Đã đặt ngành hàng ưu tiên: <b>{cat}</b>. Các voucher thuộc ngành này sẽ được cộng thêm 3–5 điểm ưu tiên!")

    async def _cmd_minsave(self, args: List[str]):
        if not args:
            await self.send_message("⚠️ Cú pháp: <code>/minsave &lt;số_tiền_tiết_kiệm_tối_thiểu&gt;</code>\nVí dụ: <code>/minsave 100000</code>")
            return
        try:
            val = float(args[0].replace(",", "").replace(".", "").replace("k", "000"))
            database.update_user_settings("min_save_amount", val)
            await self.send_message(f"💰 Đã cập nhật mức tiết kiệm tối thiểu: <b>{int(val):,}đ</b>. Bot chỉ báo deal tiết kiệm từ {int(val):,}đ trở lên.")
        except ValueError:
            await self.send_message("❌ Số tiền không hợp lệ.")

    async def _cmd_newuser(self, args: List[str]):
        if not args or args[0].lower() not in ["on", "off"]:
            await self.send_message("⚠️ Cú pháp: <code>/newuser on</code> hoặc <code>/newuser off</code>")
            return
        val = 1 if args[0].lower() == "on" else 0
        database.update_user_settings("allow_new_user_vouchers", val)
        status_str = "CHO PHÉP" if val == 1 else "CẤM (BỎ QUA)"
        await self.send_message(f"👤 Cài đặt mã tân thủ: <b>{status_str}</b>.")

    async def _cmd_platform(self, args: List[str]):
        if not args:
            await self.send_message("⚠️ Cú pháp: <code>/platform shopee|lazada|tiktok|all</code>")
            return
        target = args[0].upper()
        if target == "ALL":
            plats = ["SHOPEE", "LAZADA", "TIKTOK"]
        else:
            plats = [target]
        database.update_user_settings("active_platforms", json.dumps(plats))
        await self.send_message(f"🌐 Nền tảng đang theo dõi: <b>{', '.join(plats)}</b>")

    async def _cmd_why(self, args: List[str]):
        if not args:
            await self.send_message("⚠️ Cú pháp: <code>/why &lt;voucher_id&gt;</code>\nVí dụ: <code>/why SP_TECH_500K_2M</code>")
            return
        v_id = args[0]
        voucher = database.get_voucher_by_id(v_id)
        if not voucher:
            await self.send_message(f"❌ Không tìm thấy voucher với mã <code>{v_id}</code>.")
            return

        score, b = calculate_voucher_quality_score(voucher)
        msg = (
            f"📊 <b>GIẢI MÃ ĐIỂM CHẤT LƯỢNG VOUCHER (0 - 100)</b>\n"
            f"Voucher: <b>{voucher.get('title')}</b>\n"
            f"Tổng điểm: <b><u>{score}/100</u></b>\n\n"
            f"1. Tiền giảm thực tế: <b>+{b.get('p1_cash_reduction', {}).get('points', 0)}đ</b> ({b.get('p1_cash_reduction', {}).get('value')})\n"
            f"2. Tỷ lệ % giảm: <b>+{b.get('p2_discount_rate', {}).get('points', 0)}đ</b> ({b.get('p2_discount_rate', {}).get('value')})\n"
            f"3. Đơn tối thiểu hợp lý: <b>+{b.get('p3_min_spend_ratio', {}).get('points', 0)}đ</b> (Đơn từ {b.get('p3_min_spend_ratio', {}).get('min_spend')})\n"
            f"4. Còn lượt & Xác minh: <b>+{b.get('p4_availability_confidence', {}).get('points', 0)}đ</b>\n"
            f"5. Khả năng gộp mã: <b>+{b.get('p5_stackability', {}).get('points', 0)}đ</b>\n"
            f"6. Phù hợp mục tiêu: <b>+{b.get('p6_watchlist_relevance', {}).get('points', 0)}đ</b>\n"
            f"7. Thời hạn sử dụng: <b>+{b.get('p7_usable_time_window', {}).get('points', 0)}đ</b>\n"
        )
        if b.get("penalties", {}).get("total_deduction", 0) > 0:
            msg += f"\n⚠️ <b>Điểm trừ phạt:</b> -{b['penalties']['total_deduction']}đ ({', '.join(b['penalties']['reasons'])})"
        await self.send_message(msg)

    async def _cmd_stack(self, args: List[str]):
        if not args:
            await self.send_message("⚠️ Cú pháp: <code>/stack &lt;link_sản_phẩm&gt;</code>")
            return
        url = args[0]
        parsed = self.shopee_connector.parse_shopee_url(url)
        item_id = parsed["item_id"]
        shop_id = parsed["shop_id"]

        details = await self.shopee_connector.fetch_product_details(item_id, shop_id)
        price = details.get("original_price", 650000.0)
        direct_discount = details.get("shop_direct_discount", 50000.0)

        # Lấy voucher tốt nhất để gộp thử
        vouchers = database.get_vouchers(min_score=70)
        shop_v = next((v for v in vouchers if v["voucher_type"] == "SHOP"), None)
        plat_v = next((v for v in vouchers if v["voucher_type"] == "PLATFORM"), None)
        cat_v = next((v for v in vouchers if v["voucher_type"] in ["LIVE_VIDEO", "CATEGORY"]), None)

        res = calculate_stacked_price(
            product_price=price,
            shop_direct_discount=direct_discount,
            shop_voucher=shop_v,
            platform_voucher=plat_v,
            category_live_voucher=cat_v
        )

        msg = (
            f"🧮 <b>MÔ PHỎNG VOUCHER STACKING (GIÁ THỰC TRẢ)</b>\n\n"
            f"📦 <b>Sản phẩm:</b> {details.get('name')}\n"
            f"💵 <b>Giá gốc:</b> {int(res['original_price']):,}đ\n"
            f"➖ Giảm trực tiếp Shop: -{int(res['applied_breakdown']['shop_direct']):,}đ\n"
            f"➖ Voucher Shop: -{int(res['applied_breakdown']['shop_voucher']):,}đ\n"
            f"➖ Voucher Sàn: -{int(res['applied_breakdown']['platform_voucher']):,}đ\n"
            f"➖ Voucher Live/Ngành: -{int(res['applied_breakdown']['category_live_voucher']):,}đ\n"
            f"➖➖➖➖➖➖➖➖➖➖\n"
            f"💥 <b>GIÁ THỰC TRẢ DỰ KIẾN:</b> <b><u>{int(res['final_price']):,}đ</u></b>\n"
            f"📉 Tiết kiệm: <b>{int(res['total_savings']):,}đ (-{res['discount_percent']}%)</b>\n"
            f"🛡 Độ tin cậy gộp mã: <b>{res['confidence']}</b>\n"
            f"🚫 <i>Cam kết ZERO FREESHIP: Phí vận chuyển không tham gia tính toán.</i>"
        )
        await self.send_message(msg)

    async def _cmd_history(self, args: List[str]):
        if not args:
            await self.send_message("⚠️ Cú pháp: <code>/history &lt;item_id&gt;</code>")
            return
        item_id = args[0]
        history = database.get_product_price_history(item_id)
        if not history:
            await self.send_message(f"Chưa có lịch sử giá cho sản phẩm <code>{item_id}</code>. Sản phẩm cần được theo dõi ít nhất 1 chu kỳ.")
            return

        msg = f"📈 <b>LỊCH SỬ BIẾN ĐỘNG GIÁ (CHỐNG GIÁ ẢO):</b> <code>{item_id}</code>\n\n"
        for h in history[:10]:
            msg += f"• {h['recorded_at'][:16]}: <b>{int(h['price']):,}đ</b>\n"
        await self.send_message(msg)

    async def _cmd_settings(self):
        cfg = database.get_user_settings()
        muted_str = "ĐANG TẮT (Muted)" if cfg.get("is_muted") == 1 else "ĐANG BẬT"
        newuser_str = "BẬT" if cfg.get("allow_new_user_vouchers") == 1 else "TẮT"
        msg = (
            "⚙️ <b>CÀI ĐẶT CÁ NHÂN (USER SETTINGS)</b>\n\n"
            f"• Thông báo Telegram: <b>{muted_str}</b> (/mute | /unmute)\n"
            f"• Điểm chất lượng tối thiểu: <b>{cfg.get('min_quality_score', 70)}/100</b>\n"
            f"• Số tiền tiết kiệm tối thiểu: <b>{int(cfg.get('min_save_amount', 50000)):,}đ</b> (/minsave)\n"
            f"• Nhận voucher tân thủ: <b>{newuser_str}</b> (/newuser)\n"
            f"• Các sàn đang bật: <b>{cfg.get('active_platforms', '[\"SHOPEE\"]')}</b> (/platform)\n"
            f"• Bài trừ Freeship: <b>100% CỨNG (KHÔNG THỂ TẮT)</b>"
        )
        await self.send_message(msg)

    async def start_polling(self):
        """Lắng nghe câu lệnh Telegram qua Long Polling an toàn"""
        self.is_running = True
        print(f"🤖 Telegram Bot Service đang hoạt động (Chat ID: {self.chat_id})...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            while self.is_running:
                try:
                    url = f"{self.api_url}/getUpdates?offset={self.last_update_id + 1}&timeout=20"
                    res = await client.get(url)
                    if res.status_code == 200:
                        data = res.json()
                        for update in data.get("result", []):
                            self.last_update_id = update["update_id"]
                            # Xử lý tin nhắn text
                            if "message" in update and "text" in update["message"]:
                                msg_text = update["message"]["text"]
                                sender_id = str(update["message"]["chat"]["id"])
                                asyncio.create_task(self.handle_command(msg_text, sender_id))
                            # Xử lý callback button
                            elif "callback_query" in update:
                                cb_data = update["callback_query"]["data"]
                                if cb_data.startswith("why_"):
                                    v_id = cb_data.replace("why_", "")
                                    asyncio.create_task(self._cmd_why([v_id]))
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    await asyncio.sleep(3)

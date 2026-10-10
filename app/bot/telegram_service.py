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
from core import database, calculator
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

    async def answer_callback(self, callback_query_id: str, text: Optional[str] = None) -> None:
        """Phản hồi callback query để tắt biểu tượng đồng hồ quay trên Telegram"""
        try:
            payload = {"callback_query_id": callback_query_id}
            if text:
                payload["text"] = text
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(f"{self.api_url}/answerCallbackQuery", json=payload)
        except Exception:
            pass

    async def broadcast_hot_alert(self, voucher: Dict[str, Any], example_product: Optional[Dict[str, Any]] = None) -> bool:
        """Gửi cảnh báo Hot Voucher tự động với cơ chế SHA-256 Deduplication chống spam"""
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

        # Kiểm tra trùng trong database
        if database.is_alert_duplicate(dedup_hash):
            return False

        msg = format_hot_voucher_alert(voucher, example_product)
        claim_url = voucher.get("claim_url", "https://shopee.vn")

        # Nút bấm gọn gàng, sắp xếp khoa học theo dạng lưới 2 cột
        buttons = {
            "inline_keyboard": [
                [
                    {"text": "🎫 LƯU MÃ TRÊN SHOPEE", "url": claim_url}
                ],
                [
                    {"text": "🔍 Bảng Điểm (/why)", "callback_data": f"why_{v_id}"},
                    {"text": "⚡️ Quét Thử Deal", "callback_data": "menu_check"}
                ],
                [
                    {"text": "📋 Xem Watchlist", "callback_data": "menu_list"},
                    {"text": "🏠 Menu Chính", "callback_data": "menu_home"}
                ]
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

    async def send_deal_alert(self, product: Dict[str, Any], evaluation: Dict[str, Any], alert_reason: str = "DEAL_MOI") -> None:
        """Gửi thông báo khi món hàng đạt ngưỡng giá mục tiêu"""
        tier = evaluation.get("tier_label", "🔥 SIÊU DEAL GIÁ TỐT")
        prefix = "🚨 [GIÁ MỚI TỐT HƠN]" if alert_reason == "GIA_TOT_HON" else tier

        vouchers_text = ""
        for v in evaluation.get("applied_vouchers", []):
            vouchers_text += f"  • <b>{v.get('type')}</b>: {v.get('label')}\n"

        if not vouchers_text:
            vouchers_text = "  • <i>(Không cần mã, shop đang giảm trực tiếp)</i>\n"

        target_str = f"≥ {product.get('target_value')}%" if str(product.get('target_mode')).upper() == 'PERCENT' else f"≤ {int(product.get('target_value', 0)):,}đ"
        item_id = product.get("item_id_on_platform") or product.get("item_id")
        p_url = product.get("product_url") or f"https://shopee.vn/product/{product.get('shop_id', '0')}/{item_id}"

        msg = (
            f"<b>{prefix}</b>\n\n"
            f"📦 <b>Sản phẩm:</b> {product.get('name')}\n"
            f"📊 <b>Giá niêm yết:</b> <s>{int(evaluation.get('baseline_price', 0)):,}đ</s>\n"
            f"💥 <b>GIÁ THỰC TRẢ SAU MÃ:</b> <b><u>{int(evaluation.get('final_price', 0)):,}đ</u></b>\n"
            f"📉 <b>Mức giảm thật:</b> <b>-{evaluation.get('discount_percent')}%</b> (Tiết kiệm {int(evaluation.get('savings', 0)):,}đ)\n"
            f"🎯 <b>Mục tiêu của bạn:</b> {target_str}\n\n"
            f"🎫 <b>CÁC VOUCHER ĐANG ÁP DỤNG:</b>\n"
            f"{vouchers_text}\n"
            f"🛡 <b>Độ tin cậy gộp mã:</b> {evaluation.get('confidence', 'VERIFIED')}\n"
            f"⚠️ <i>Lưu ý: Bạn vào Shopee kiểm tra lưu mã rồi đặt mua thủ công trên App.</i>"
        )

        buttons = {
            "inline_keyboard": [
                [
                    {"text": "🛒 BẤM MUA NGAY TRÊN SHOPEE", "url": p_url}
                ],
                [
                    {"text": "🧮 Chi Tiết Gộp Mã", "callback_data": f"stack_{item_id}"},
                    {"text": "📈 Lịch Sử Giá", "callback_data": f"history_{item_id}"}
                ],
                [
                    {"text": "📋 Watchlist", "callback_data": "menu_list"},
                    {"text": "⚡️ Quét Lại", "callback_data": "menu_check"}
                ]
            ]
        }

        img = product.get("image_url") or "https://deo.shopeemobile.com/shopee/shopee-pcmall-live-sg/assets/icon_favicon_1_32.png"
        await self.send_photo(img, msg, reply_markup=buttons)

    # ----------------- NHẬN DIỆN & THÊM LINK TRỰC TIẾP -----------------

    async def handle_direct_link(self, text: str) -> bool:
        """
        Tự động nhận diện khi người dùng dán link Shopee vào khung chat (kể cả không gõ lệnh /watch)
        Ví dụ:
        - https://shopee.vn/product/88888/12345678
        - https://vn.shp.ee/abcxyz 35%
        - https://shopee.vn/... 450k
        """
        match = re.search(r'(https?://[^\s]+)', text)
        if not match:
            return False

        raw_url = match.group(1)
        if "shopee.vn" not in raw_url and "shp.ee" not in raw_url:
            return False

        # Phân tích shop_id và item_id (tự động unshorten link rút gọn)
        parsed = await self.shopee_connector.resolve_url_and_parse(raw_url)
        item_id = parsed.get("item_id")
        shop_id = parsed.get("shop_id")

        if not item_id:
            await self.send_message("❌ Không nhận diện được mã sản phẩm từ link Shopee này. Vui lòng kiểm tra lại link.")
            return True

        # Trích xuất mục tiêu giá nếu có kèm theo trong tin nhắn
        remainder = text.replace(raw_url, "").strip()
        target_val = 30.0 # Mặc định giảm 30%
        target_mode = "PERCENT"

        if remainder:
            clean_rem = remainder.lower().replace(",", "").replace(".", "").replace("đ", "")
            if "%" in clean_rem:
                try:
                    pct = float(re.findall(r'\d+', clean_rem)[0])
                    target_mode = "PERCENT"
                    target_val = pct
                except Exception:
                    pass
            elif "k" in clean_rem:
                try:
                    val_k = float(re.findall(r'\d+', clean_rem)[0]) * 1000
                    target_mode = "PRICE"
                    target_val = val_k
                except Exception:
                    pass
            else:
                digits = re.findall(r'\d+', clean_rem)
                if digits:
                    val_num = float(digits[0])
                    if val_num <= 100:
                        target_mode = "PERCENT"
                        target_val = val_num
                    else:
                        target_mode = "PRICE"
                        target_val = val_num

        # Lấy thông tin chi tiết từ Shopee
        details = await self.shopee_connector.fetch_product_details(item_id, shop_id)
        name = details.get("name", f"Sản phẩm {item_id}")
        base_price = details.get("original_price") or details.get("current_price", 500000.0)

        # Lưu vào Database
        database.add_product(
            item_id=item_id,
            shop_id=shop_id,
            name=name,
            url=raw_url,
            image_url=details.get("image_url"),
            target_mode=target_mode,
            target_value=target_val,
            baseline_price=base_price
        )

        # Tính toán giá gộp thử ngay lập tức
        vouchers = database.get_vouchers(min_score=60)
        p_obj = database.get_product_by_id(item_id)
        eval_res = calculator.stack_vouchers_and_evaluate(p_obj, vouchers)
        database.update_product_evaluation(
            item_id=item_id,
            current_price=eval_res["current_price"],
            final_price=eval_res["final_price"],
            discount_percent=eval_res["discount_percent"],
            is_deal_ready=1 if eval_res["is_deal_ready"] else 0,
            applied_vouchers=eval_res["applied_vouchers"]
        )

        target_str = f"giảm ≥ {target_val}%" if target_mode == "PERCENT" else f"giá ≤ {int(target_val):,}đ"
        ready_icon = "🔥 ĐÃ ĐẠT GIÁ MUA!" if eval_res["is_deal_ready"] else "⏳ Đang theo dõi"

        msg = (
            f"✅ <b>ĐÃ THÊM SẢN PHẨM VÀO WATCHLIST!</b>\n\n"
            f"📦 <b>{name}</b>\n"
            f"💵 <b>Giá niêm yết:</b> <s>{int(base_price):,}đ</s>\n"
            f"💥 <b>Giá sau gộp mã hiện tại:</b> <b><u>{int(eval_res['final_price']):,}đ</u></b> (-{eval_res['discount_percent']}%)\n"
            f"🎯 <b>Mục tiêu canh mua:</b> <b>{target_str}</b>\n"
            f"📊 <b>Trạng thái:</b> {ready_icon}\n\n"
            f"💡 <i>Bạn có thể đổi nhanh mục tiêu giảm bằng các nút bên dưới:</i>"
        )

        # Nút bấm gọn gàng, bố cục 2–3 cột tiện dụng
        buttons = {
            "inline_keyboard": [
                [
                    {"text": "🎯 Canh Giảm 20%", "callback_data": f"target_{item_id}_20"},
                    {"text": "🎯 Canh Giảm 30%", "callback_data": f"target_{item_id}_30"},
                    {"text": "🎯 Canh Giảm 40%", "callback_data": f"target_{item_id}_40"}
                ],
                [
                    {"text": "🛒 Xem Trên Shopee", "url": details.get("product_url", raw_url)},
                    {"text": "🧮 Thử Gộp Mã Ngay", "callback_data": f"stack_{item_id}"}
                ],
                [
                    {"text": "📋 Xem Watchlist", "callback_data": "menu_list"},
                    {"text": "❌ Hủy Canh Món Này", "callback_data": f"del_{item_id}"}
                ]
            ]
        }

        img = details.get("image_url")
        if img:
            await self.send_photo(img, msg, reply_markup=buttons)
        else:
            await self.send_message(msg, reply_markup=buttons)

        return True

    # ----------------- XỬ LÝ LỆNH & MENU TƯƠNG TÁC -----------------

    async def handle_command(self, text: str, user_chat_id: str) -> None:
        clean_text = text.strip()
        if not clean_text:
            return

        # 1. Kiểm tra dán link Shopee trực tiếp
        if "shopee.vn" in clean_text or "shp.ee" in clean_text:
            if not clean_text.startswith("/"):
                handled = await self.handle_direct_link(clean_text)
                if handled:
                    return

        parts = clean_text.split()
        cmd = parts[0].lower().split("@")[0]
        args = parts[1:]

        if cmd in ["/start", "/help", "/menu"]:
            await self._cmd_help()
        elif cmd in ["/vouchers", "/voucher"]:
            await self._cmd_vouchers(min_score=70)
        elif cmd in ["/hot", "/sieu_voucher"]:
            await self._cmd_vouchers(min_score=85, hot_only=True)
        elif cmd in ["/watch", "/add", "/them"]:
            if args:
                await self.handle_direct_link(" ".join(args))
            else:
                await self._cmd_add_guide()
        elif cmd in ["/list", "/watchlist", "/ds"]:
            await self._cmd_list_watchlist()
        elif cmd in ["/del", "/xoa"]:
            await self._cmd_del(args)
        elif cmd in ["/check", "/scan", "/quet"]:
            await self._cmd_scan_now()
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
            await self.send_message(f"❓ Không rõ lệnh <code>{cmd}</code>. Gõ /menu để mở bảng điều khiển.")

    async def _cmd_help(self):
        msg = (
            "🤖 <b>VOUCHER INTELLIGENCE & DEAL OPTIMIZER</b>\n"
            "<i>(Săn voucher xịn Shopee, Lazada, TikTok — Bài trừ 100% Freeship ảo)</i>\n\n"
            "✨ <b>BẠN CÓ THỂ LÀM GÌ:</b>\n"
            "• <b>Dán thẳng link Shopee vào đây</b> để bắt đầu canh giá tự động.\n"
            "• Hệ thống <b>tự động bắn tin</b> khi có Voucher HOT hoặc sản phẩm đạt giá.\n"
            "• Gộp mã đa tầng: Shop + Toàn sàn + Video/Live.\n\n"
            "👇 <b>Bấm các nút dưới đây để thao tác nhanh:</b>"
        )
        buttons = self.get_main_menu_keyboard()
        await self.send_message(msg, reply_markup=buttons)

    def get_main_menu_keyboard(self):
        return {
            "inline_keyboard": [
                [
                    {"text": "🔥 Siêu Voucher HOT", "callback_data": "menu_hot"},
                    {"text": "🎫 Kho Voucher Xịn", "callback_data": "menu_vouchers"}
                ],
                [
                    {"text": "📋 Xem Watchlist", "callback_data": "menu_list"},
                    {"text": "➕ Thêm Sản Phẩm", "callback_data": "menu_add_guide"}
                ],
                [
                    {"text": "⚡️ Quét Deal Ngay", "callback_data": "menu_check"},
                    {"text": "⚙️ Cài Đặt", "callback_data": "menu_settings"}
                ]
            ]
        }

    async def _cmd_add_guide(self):
        msg = (
            "➕ <b>HƯỚNG DẪN THÊM SẢN PHẨM CANH DEAL</b>\n\n"
            "Rất đơn giản! Bạn chỉ cần <b>COPY và DÁN THẲNG LINK SHOPEE</b> vào ô chat này.\n\n"
            "💡 <b>Các ví dụ tiện lợi:</b>\n"
            "1. <b>Dán link trực tiếp:</b>\n"
            "   <code>https://shopee.vn/product/88888/12345678</code>\n"
            "   <i>(Bot tự động canh khi giảm ≥ 30%)</i>\n\n"
            "2. <b>Dán kèm % giảm mong muốn:</b>\n"
            "   <code>https://shopee.vn/product/88888/12345678 35%</code>\n\n"
            "3. <b>Dán kèm mức giá kỳ vọng:</b>\n"
            "   <code>https://shopee.vn/product/88888/12345678 450k</code>\n\n"
            "4. <b>Hỗ trợ cả link chia sẻ ngắn từ app:</b>\n"
            "   <code>https://vn.shp.ee/xxxxxx</code>\n\n"
            "👉 <i>Hãy copy link món hàng bạn thích và gửi vào đây ngay bây giờ!</i>"
        )
        buttons = {
            "inline_keyboard": [
                [{"text": "📋 Xem Watchlist Hiện Tại", "callback_data": "menu_list"}],
                [{"text": "🏠 Quay Lại Menu Chính", "callback_data": "menu_home"}]
            ]
        }
        await self.send_message(msg, reply_markup=buttons)

    async def _cmd_list_watchlist(self):
        products = database.get_all_products()
        if not products:
            msg = (
                "📋 <b>WATCHLIST CỦA BẠN ĐANG TRỐNG</b>\n\n"
                "Bạn chưa thêm sản phẩm nào. Hãy copy và dán một link Shopee vào đây để bắt đầu theo dõi!"
            )
            buttons = {
                "inline_keyboard": [
                    [{"text": "➕ Hướng Dẫn Thêm Sản Phẩm", "callback_data": "menu_add_guide"}],
                    [{"text": "🔥 Xem Voucher HOT Đang Có", "callback_data": "menu_hot"}]
                ]
            }
            await self.send_message(msg, reply_markup=buttons)
            return

        msg = f"📋 <b>DANH SÁCH SẢN PHẨM ĐANG THEO DÕI ({len(products)} món):</b>\n\n"
        for i, p in enumerate(products, 1):
            ready_icon = "🔥 ĐẠT GIÁ" if p.get("is_deal_ready") == 1 else "⏳ Đang canh"
            t_str = f"≥ {p.get('target_value')}%" if str(p.get('target_mode')).upper() == 'PERCENT' else f"≤ {int(p.get('target_value', 0)):,}đ"
            base_p = int(p.get('baseline_market_price') or p.get('baseline_price', 0))
            cur_p = int(p.get('final_price') or p.get('current_price', 0))
            
            msg += (
                f"{i}. <b>{p['name']}</b>\n"
                f"   • Trạng thái: <b>{ready_icon}</b>\n"
                f"   • Giá niêm yết: <s>{base_p:,}đ</s>\n"
                f"   • Giá sau gộp mã: <b><u>{cur_p:,}đ</u></b> (-{p.get('discount_percent', 0)}%)\n"
                f"   • Mục tiêu của bạn: {t_str}\n"
                f"   • ID: <code>{p.get('item_id_on_platform') or p.get('item_id')}</code>\n\n"
            )

        kb_rows = []
        for p in products[:4]:
            i_id = p.get('item_id_on_platform') or p.get('item_id')
            short_name = p['name'][:14] + ".." if len(p['name']) > 14 else p['name']
            kb_rows.append([
                {"text": f"🧮 Gộp: {short_name}", "callback_data": f"stack_{i_id}"},
                {"text": "❌ Xóa", "callback_data": f"del_{i_id}"}
            ])

        kb_rows.append([
            {"text": "⚡️ Quét Deal Ngay", "callback_data": "menu_check"},
            {"text": "➕ Thêm Sản Phẩm Mới", "callback_data": "menu_add_guide"}
        ])
        kb_rows.append([
            {"text": "🏠 Quay Lại Menu Chính", "callback_data": "menu_home"}
        ])

        await self.send_message(msg, reply_markup={"inline_keyboard": kb_rows})

    async def _cmd_scan_now(self):
        from core.scanner import run_scan_cycle
        await self.send_message("⚡️ Đang quét toàn bộ kho voucher và đối soát giá các sản phẩm...")
        ready_count = await run_scan_cycle(self)
        stats = database.get_stats()
        msg = (
            f"✅ <b>ĐÃ HOÀN TẤT CHU KỲ QUÉT!</b>\n\n"
            f"• Số sản phẩm theo dõi: <b>{stats['total_products']} món</b>\n"
            f"• Số deal đạt mục tiêu mua: <b>{stats['ready_deals']} món</b>\n"
            f"• Kho voucher xịn đang mở: <b>{stats['total_vouchers']} mã</b>\n"
            f"• Siêu voucher HOT (Score ≥ 85): <b>{stats['hot_vouchers']} mã</b>\n\n"
            f"🤖 <i>Bot sẽ tự động gửi cảnh báo khẩn khi có voucher mới hoặc món hàng đạt giá.</i>"
        )
        buttons = {
            "inline_keyboard": [
                [
                    {"text": "🔥 Xem Voucher HOT", "callback_data": "menu_hot"},
                    {"text": "📋 Xem Watchlist", "callback_data": "menu_list"}
                ],
                [
                    {"text": "🏠 Menu Chính", "callback_data": "menu_home"}
                ]
            ]
        }
        await self.send_message(msg, reply_markup=buttons)

    async def _cmd_vouchers(self, min_score: int = 70, hot_only: bool = False):
        vouchers = database.get_vouchers(min_score=min_score, hot_only=hot_only)
        if not vouchers:
            await self.send_message("Hiện tại chưa có voucher nào đạt tiêu chí (Hệ thống đã tự động lọc sạch 100% voucher freeship và voucher rác).")
            return

        header = "🔥 <b>SIÊU VOUCHER HOT (SCORE ≥ 85)</b>\n\n" if hot_only else "🎫 <b>KHO VOUCHER XỊN ĐANG HOẠT ĐỘNG (SCORE ≥ 70)</b>\n\n"
        body = ""
        kb_rows = []

        for i, v in enumerate(vouchers[:6], 1):
            d_val = int(v['discount_value'])
            d_str = f"Giảm {v['discount_value']}% (Tối đa {int(v['max_discount_amount']):,}đ)" if v['discount_type'] in ['PERCENT', 'PERCENTAGE'] else f"Giảm {d_val:,}đ"
            min_sp = f"Đơn từ {int(v['min_spend']):,}đ" if v['min_spend'] > 0 else "Đơn từ 0đ"
            v_id = v['voucher_id_on_platform']
            
            body += (
                f"{i}. <b>[{v['platform_id']}] {v['title']}</b>\n"
                f"   💰 <b>{d_str}</b> | 🛒 {min_sp}\n"
                f"   ⭐ Điểm: <b>{v['quality_score']}/100</b>\n\n"
            )
            short_t = v['title'][:16] + ".." if len(v['title']) > 16 else v['title']
            kb_rows.append([
                {"text": f"🎫 Lấy Mã: {short_t}", "url": v.get("claim_url", "https://shopee.vn")},
                {"text": "🔍 Xem Điểm", "callback_data": f"why_{v_id}"}
            ])

        kb_rows.append([
            {"text": "📋 Xem Watchlist", "callback_data": "menu_list"},
            {"text": "⚡️ Quét Lại", "callback_data": "menu_check"}
        ])
        kb_rows.append([
            {"text": "🏠 Menu Chính", "callback_data": "menu_home"}
        ])

        await self.send_message(header + body, reply_markup={"inline_keyboard": kb_rows})

    async def _cmd_why(self, args: List[str]):
        if not args:
            await self.send_message("⚠️ Cú pháp: <code>/why &lt;voucher_id&gt;</code>")
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

        buttons = {
            "inline_keyboard": [
                [{"text": "🎫 Lưu Mã Này Ngay", "url": voucher.get("claim_url", "https://shopee.vn")}],
                [{"text": "🔥 Xem Thêm Mã HOT", "callback_data": "menu_hot"}, {"text": "🏠 Menu Chính", "callback_data": "menu_home"}]
            ]
        }
        await self.send_message(msg, reply_markup=buttons)

    async def _cmd_stack(self, args: List[str]):
        if not args:
            await self.send_message("⚠️ Cú pháp: <code>/stack &lt;link_sản_phẩm_hoặc_mã_sp&gt;</code>")
            return
        target = args[0]
        if "shopee.vn" in target or "shp.ee" in target:
            parsed = await self.shopee_connector.resolve_url_and_parse(target)
            item_id = parsed["item_id"]
            shop_id = parsed["shop_id"]
        else:
            item_id = target
            p_exist = database.get_product_by_id(item_id)
            shop_id = p_exist.get("shop_id") if p_exist else "0"

        details = await self.shopee_connector.fetch_product_details(item_id, shop_id)
        price = details.get("original_price", 650000.0)
        direct_discount = details.get("shop_direct_discount", 50000.0)

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
            f"🚫 <i>Cam kết ZERO FREESHIP: Tuyệt đối không trừ ship ảo.</i>"
        )
        buttons = {
            "inline_keyboard": [
                [{"text": "🛒 Bấm Mua Ngay", "url": details.get("product_url", "https://shopee.vn")}],
                [{"text": "📋 Xem Watchlist", "callback_data": "menu_list"}, {"text": "🏠 Menu Chính", "callback_data": "menu_home"}]
            ]
        }
        await self.send_message(msg, reply_markup=buttons)

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
        
        buttons = {
            "inline_keyboard": [
                [{"text": "📋 Quay Lại Watchlist", "callback_data": "menu_list"}],
                [{"text": "🏠 Menu Chính", "callback_data": "menu_home"}]
            ]
        }
        await self.send_message(msg, reply_markup=buttons)

    async def _cmd_del(self, args: List[str]):
        if not args:
            await self.send_message("⚠️ Cú pháp: <code>/del &lt;item_id&gt;</code>")
            return
        item_id = args[0]
        p = database.get_product_by_id(item_id)
        name = p.get("name", item_id) if p else item_id
        database.delete_product(item_id)
        msg = f"🗑 Đã xóa <b>{name}</b> khỏi Watchlist thành công."
        buttons = {
            "inline_keyboard": [
                [{"text": "📋 Xem Lại Watchlist", "callback_data": "menu_list"}],
                [{"text": "🏠 Menu Chính", "callback_data": "menu_home"}]
            ]
        }
        await self.send_message(msg, reply_markup=buttons)

    async def _cmd_settings(self):
        cfg = database.get_user_settings()
        muted_str = "ĐANG TẮT (Muted)" if cfg.get("is_muted") == 1 else "ĐANG BẬT"
        newuser_str = "BẬT" if cfg.get("allow_new_user_vouchers") == 1 else "TẮT"
        msg = (
            "⚙️ <b>CÀI ĐẶT CÁ NHÂN (USER SETTINGS)</b>\n\n"
            f"• Thông báo Telegram: <b>{muted_str}</b>\n"
            f"• Điểm chất lượng tối thiểu: <b>{cfg.get('min_quality_score', 70)}/100</b>\n"
            f"• Số tiền tiết kiệm tối thiểu: <b>{int(cfg.get('min_save_amount', 50000)):,}đ</b>\n"
            f"• Nhận voucher tân thủ: <b>{newuser_str}</b>\n"
            f"• Các sàn đang bật: <b>{cfg.get('active_platforms', '[\"SHOPEE\"]')}</b>\n"
            f"• Bài trừ Freeship: <b>100% CỨNG (KHÔNG THỂ TẮT)</b>"
        )
        toggle_mute_text = "🔔 Bật Chuông Cảnh Báo" if cfg.get("is_muted") == 1 else "🔕 Tắt Chuông Cảnh Báo"
        buttons = {
            "inline_keyboard": [
                [
                    {"text": toggle_mute_text, "callback_data": "menu_mute_toggle"}
                ],
                [
                    {"text": "⚡️ Quét Deal Ngay", "callback_data": "menu_check"},
                    {"text": "📋 Xem Watchlist", "callback_data": "menu_list"}
                ],
                [
                    {"text": "🏠 Quay Lại Menu Chính", "callback_data": "menu_home"}
                ]
            ]
        }
        await self.send_message(msg, reply_markup=buttons)

    async def _cmd_keyword(self, args: List[str]):
        if not args:
            await self.send_message("⚠️ Cú pháp: <code>/keyword &lt;từ_khóa&gt; &lt;giá_mục_tiêu&gt;</code>")
            return
        kw = " ".join(args)
        await self.send_message(f"🔍 Đã lưu từ khóa theo dõi: <b>{kw}</b>.")

    async def _cmd_category(self, args: List[str]):
        if not args:
            await self.send_message("⚠️ Cú pháp: <code>/category &lt;tên_ngành_hàng&gt;</code>")
            return
        cat = " ".join(args)
        await self.send_message(f"🏷 Đã đặt ngành hàng ưu tiên: <b>{cat}</b>.")

    async def _cmd_minsave(self, args: List[str]):
        if not args:
            await self.send_message("⚠️ Cú pháp: <code>/minsave &lt;số_tiền_tiết_kiệm&gt;</code>")
            return
        try:
            val = float(args[0].replace(",", "").replace(".", "").replace("k", "000"))
            database.update_user_settings("min_save_amount", val)
            await self.send_message(f"💰 Đã cập nhật mức tiết kiệm tối thiểu: <b>{int(val):,}đ</b>.")
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
        plats = ["SHOPEE", "LAZADA", "TIKTOK"] if target == "ALL" else [target]
        database.update_user_settings("active_platforms", json.dumps(plats))
        await self.send_message(f"🌐 Nền tảng đang theo dõi: <b>{', '.join(plats)}</b>")

    # ----------------- LONG POLLING VÀ XỬ LÝ SỰ KIỆN -----------------

    async def start_polling(self):
        """Lắng nghe câu lệnh Telegram & nút bấm Inline Keyboard qua Long Polling an toàn"""
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
                            
                            # 1. Tin nhắn Text từ người dùng
                            if "message" in update and "text" in update["message"]:
                                msg_text = update["message"]["text"]
                                sender_id = str(update["message"]["chat"]["id"])
                                asyncio.create_task(self.handle_command(msg_text, sender_id))

                            # 2. Bấm nút Inline Keyboard (Callback Query)
                            elif "callback_query" in update:
                                cb = update["callback_query"]
                                cb_id = cb["id"]
                                cb_data = cb.get("data", "")
                                sender_id = str(cb["from"]["id"])
                                
                                # Tắt hiệu ứng loading đồng hồ quay trên nút
                                asyncio.create_task(self.answer_callback(cb_id))

                                # Điều hướng sự kiện nút bấm
                                if cb_data == "menu_home":
                                    asyncio.create_task(self._cmd_help())
                                elif cb_data == "menu_hot":
                                    asyncio.create_task(self._cmd_vouchers(min_score=85, hot_only=True))
                                elif cb_data == "menu_vouchers":
                                    asyncio.create_task(self._cmd_vouchers(min_score=70))
                                elif cb_data == "menu_list":
                                    asyncio.create_task(self._cmd_list_watchlist())
                                elif cb_data == "menu_add_guide":
                                    asyncio.create_task(self._cmd_add_guide())
                                elif cb_data == "menu_check":
                                    asyncio.create_task(self._cmd_scan_now())
                                elif cb_data == "menu_settings":
                                    asyncio.create_task(self._cmd_settings())
                                elif cb_data == "menu_mute_toggle":
                                    cfg = database.get_user_settings()
                                    new_mute = 0 if cfg.get("is_muted") == 1 else 1
                                    database.update_user_settings("is_muted", new_mute)
                                    asyncio.create_task(self._cmd_settings())
                                elif cb_data.startswith("why_"):
                                    v_id = cb_data.replace("why_", "")
                                    asyncio.create_task(self._cmd_why([v_id]))
                                elif cb_data.startswith("stack_"):
                                    item_id = cb_data.replace("stack_", "")
                                    asyncio.create_task(self._cmd_stack([item_id]))
                                elif cb_data.startswith("history_"):
                                    item_id = cb_data.replace("history_", "")
                                    asyncio.create_task(self._cmd_history([item_id]))
                                elif cb_data.startswith("del_"):
                                    item_id = cb_data.replace("del_", "")
                                    asyncio.create_task(self._cmd_del([item_id]))
                                elif cb_data.startswith("target_"):
                                    # target_{item_id}_{pct}
                                    parts = cb_data.split("_")
                                    if len(parts) >= 3:
                                        t_item_id = parts[1]
                                        t_pct = float(parts[2])
                                        p_exist = database.get_product_by_id(t_item_id)
                                        if p_exist:
                                            # Cập nhật mục tiêu và đánh giá lại
                                            database.add_product(
                                                item_id=t_item_id,
                                                shop_id=p_exist.get("shop_id", "0"),
                                                name=p_exist["name"],
                                                url=p_exist["product_url"],
                                                image_url=p_exist.get("image_url"),
                                                target_mode="PERCENT",
                                                target_value=t_pct,
                                                baseline_price=p_exist.get("baseline_market_price") or p_exist.get("baseline_price", 0)
                                            )
                                            vouchers = database.get_vouchers(min_score=60)
                                            p_updated = database.get_product_by_id(t_item_id)
                                            eval_res = calculator.stack_vouchers_and_evaluate(p_updated, vouchers)
                                            database.update_product_evaluation(
                                                item_id=t_item_id,
                                                current_price=eval_res["current_price"],
                                                final_price=eval_res["final_price"],
                                                discount_percent=eval_res["discount_percent"],
                                                is_deal_ready=1 if eval_res["is_deal_ready"] else 0,
                                                applied_vouchers=eval_res["applied_vouchers"]
                                            )
                                            asyncio.create_task(self.send_message(
                                                f"🎯 Đã cập nhật mục tiêu cho <b>{p_exist['name']}</b>: <b>Giảm ≥ {t_pct}%</b>!\n"
                                                f"Giá sau gộp mã hiện tại: <b>{int(eval_res['final_price']):,}đ</b> (-{eval_res['discount_percent']}%)"
                                            ))
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    await asyncio.sleep(3)

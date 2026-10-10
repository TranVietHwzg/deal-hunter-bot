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
from app.bot.templates import format_hot_voucher_alert, format_restock_alert, get_voucher_shop_scope
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
        self.pending_price_input: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _parse_price_from_text(text: str) -> Optional[float]:
        """Trích xuất giá tiền thông minh: 100k, 95k, 95.000đ, 95000, 1.5tr, 15tr, v.v."""
        if not text:
            return None
        clean = text.lower().replace(" ", "").replace("đ", "").replace("vnd", "")
        
        # Triệu / tr / m
        m_tr = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:tr|trieu|m)', clean)
        if m_tr:
            try:
                return float(m_tr.group(1).replace(",", ".")) * 1_000_000
            except ValueError:
                pass

        # k / nghìn
        m_k = re.search(r'(\d+(?:[.,]\d+)?)\s*k', clean)
        if m_k:
            try:
                return float(m_k.group(1).replace(",", ".")) * 1_000
            except ValueError:
                pass

        # Dạng số có dấu chấm/phẩy: 95.000 hoặc 100,000
        m_dots = re.search(r'(\d{1,3}(?:[.,]\d{3})+)', clean)
        if m_dots:
            raw_num = m_dots.group(1).replace(".", "").replace(",", "")
            try:
                return float(raw_num)
            except ValueError:
                pass

        # Dạng số nguyên thuần túy (từ 1.000 đến 1 tỷ)
        m_pure = re.findall(r'\b\d{4,10}\b', clean)
        if m_pure:
            try:
                return float(m_pure[0])
            except ValueError:
                pass

        # Người dùng chỉ gõ số nhỏ (VD: 95 hoặc 120)
        m_small = re.findall(r'\b\d{2,3}\b', clean)
        if m_small and (len(text.strip()) <= 5):
            try:
                val = float(m_small[0])
                if val <= 500:
                    return val * 1000
            except ValueError:
                pass

        return None

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
        """Gửi cảnh báo voucher tự động với mã nhập tay / mã ẩn để chạm sao chép"""
        user_cfg = database.get_user_settings()
        if user_cfg.get("is_muted") == 1:
            return False

        # Bài trừ freeship tuyệt đối trước khi gửi
        is_ship, _ = is_freeship(voucher)
        if is_ship:
            return False

        # Tạo hash SHA-256 để chống gửi trùng lặp
        v_id = voucher.get("id") or voucher.get("voucher_id_on_platform")
        code = voucher.get("voucher_code") or ""
        hash_input = f"HOT_{v_id}_{code}_{voucher.get('discount_value')}"
        dedup_hash = hashlib.sha256(hash_input.encode("utf-8")).hexdigest()

        # Kiểm tra trùng trong database
        if database.is_alert_duplicate(dedup_hash):
            return False

        msg = format_hot_voucher_alert(voucher, example_product)
        claim_url = voucher.get("claim_url", "https://shopee.vn")

        # Nút bấm siêu gọn gàng, xếp 2 cột
        buttons = {
            "inline_keyboard": [
                [
                    {"text": "🛒 MỞ SHOPEE ÁP MÃ NGAY", "url": claim_url}
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
                voucher_id=v_id
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

    async def handle_direct_link(self, text: str, user_chat_id: Optional[str] = None) -> bool:
        """
        Tự động nhận diện khi người dùng dán link Shopee vào khung chat.
        - Nếu có kèm giá muốn đạt được (VD: link 100k): Lưu ngay mục tiêu, tuyệt đối KHÔNG gán giá giả 750k.
        - Nếu chỉ gửi mỗi link trần: Hỏi người dùng mức giá muốn đạt được.
        """
        match = re.search(r'(https?://[^\s]+)', text)
        if not match:
            return False

        raw_url = match.group(1).rstrip(".,;!?'\")>")
        if "shopee.vn" not in raw_url and "shp.ee" not in raw_url:
            return False

        # Phân tích shop_id và item_id (tự động unshorten link rút gọn)
        parsed = await self.shopee_connector.resolve_url_and_parse(raw_url)
        item_id = parsed.get("item_id")
        shop_id = parsed.get("shop_id")

        if not item_id:
            await self.send_message("❌ Không nhận diện được mã sản phẩm từ link Shopee này. Vui lòng kiểm tra lại link.")
            return True

        # Trích xuất giá muốn đạt được nếu có kèm theo trong tin nhắn (VD: link 100k hoặc link 95000)
        remainder = text.replace(match.group(1), "").strip()
        target_price = self._parse_price_from_text(remainder)

        details = await self.shopee_connector.fetch_product_details(
            item_id,
            shop_id,
            name_hint=parsed.get("name"),
            image_hint=parsed.get("image_url"),
            price_hint=target_price
        )
        name = details.get("name", f"Sản phẩm {item_id}")
        img = details.get("image_url")

        # TRƯỜNG HỢP 1: Người dùng CÓ kèm giá muốn đạt được (Ví dụ: link 100k, link 95000)
        if target_price and target_price > 0:
            database.add_product(
                item_id=item_id,
                shop_id=shop_id,
                name=name,
                url=raw_url,
                image_url=img,
                target_mode="PRICE",
                target_value=target_price,
                baseline_price=target_price
            )

            database.update_product_evaluation(
                item_id=item_id,
                current_price=target_price,
                final_price=target_price,
                discount_percent=0,
                is_deal_ready=0,
                applied_vouchers=[]
            )

            msg = (
                f"✅ <b>ĐÃ THÊM SẢN PHẨM VÀO WATCHLIST!</b>\n\n"
                f"📦 <b>{name}</b>\n"
                f"🎯 <b>Giá muốn đạt được:</b> <b><u>≤ {int(target_price):,}đ</u></b>\n"
                f"⏳ <b>Trạng thái:</b> Đang theo dõi voucher & đợt giảm giá...\n\n"
                f"💡 <i>Bot sẽ bắn cảnh báo ngay khi phát hiện voucher giúp mua món này với giá ≤ {int(target_price):,}đ!</i>"
            )

            buttons = {
                "inline_keyboard": [
                    [
                        {"text": "🎯 Đổi Giá Muốn Đạt", "callback_data": f"chtarget_{item_id}"},
                        {"text": "🛒 Xem Trên Shopee", "url": details.get("product_url", raw_url)}
                    ],
                    [
                        {"text": "📋 Xem Watchlist", "callback_data": "menu_list"},
                        {"text": "❌ Hủy Canh Món Này", "callback_data": f"del_{item_id}"}
                    ]
                ]
            }

            if img:
                await self.send_photo(img, msg, reply_markup=buttons)
            else:
                await self.send_message(msg, reply_markup=buttons)
            return True

        # TRƯỜNG HỢP 2: Người dùng CHỈ GỬI LINK (Chưa kèm giá muốn đạt được)
        # Lưu vào trạng thái chờ nhập giá, KHÔNG tự ý gán giá giả định!
        chat_key = str(user_chat_id or self.chat_id)
        self.pending_price_input[chat_key] = {
            "action": "new_product",
            "item_id": item_id,
            "shop_id": shop_id,
            "name": name,
            "url": raw_url,
            "image_url": img
        }

        msg = (
            f"📦 <b>{name}</b>\n\n"
            f"🎯 <b>Bạn muốn mua món này với giá bao nhiêu?</b>\n"
            f"<i>(Chỉ cần nhắn số tiền bạn muốn đạt được, ví dụ: <code>100k</code> hoặc <code>95000</code>)</i>"
        )

        buttons = {
            "inline_keyboard": [
                [
                    {"text": "🛒 Xem Trước Trên Shopee", "url": details.get("product_url", raw_url)}
                ]
            ]
        }

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

        chat_key = str(user_chat_id or self.chat_id)

        # 1. Kiểm tra xem người dùng có đang trả lời giá cho sản phẩm vừa gửi không
        if chat_key in self.pending_price_input and not clean_text.startswith("/") and "shopee.vn" not in clean_text and "shp.ee" not in clean_text:
            target_price = self._parse_price_from_text(clean_text)
            if target_price and target_price > 0:
                pending = self.pending_price_input.pop(chat_key)
                item_id = pending["item_id"]
                
                if pending.get("action") == "update_target":
                    p_exist = database.get_product_by_id(item_id)
                    p_name = p_exist["name"] if p_exist else pending.get("name", item_id)
                    p_url = p_exist["product_url"] if p_exist else pending.get("url", "https://shopee.vn")
                    p_img = p_exist.get("image_url") if p_exist else pending.get("image_url")
                    
                    database.add_product(
                        item_id=item_id,
                        shop_id=p_exist.get("shop_id", "0") if p_exist else "0",
                        name=p_name,
                        url=p_url,
                        image_url=p_img,
                        target_mode="PRICE",
                        target_value=target_price,
                        baseline_price=target_price
                    )
                    database.update_product_evaluation(
                        item_id=item_id,
                        current_price=target_price,
                        final_price=target_price,
                        discount_percent=0,
                        is_deal_ready=0,
                        applied_vouchers=[]
                    )
                    await self.send_message(
                        f"🎯 Đã cập nhật giá muốn đạt được cho <b>{p_name}</b> thành: <b><u>≤ {int(target_price):,}đ</u></b>!"
                    )
                    return
                else:
                    # new_product
                    database.add_product(
                        item_id=item_id,
                        shop_id=pending.get("shop_id", "0"),
                        name=pending["name"],
                        url=pending["url"],
                        image_url=pending.get("image_url"),
                        target_mode="PRICE",
                        target_value=target_price,
                        baseline_price=target_price
                    )
                    database.update_product_evaluation(
                        item_id=item_id,
                        current_price=target_price,
                        final_price=target_price,
                        discount_percent=0,
                        is_deal_ready=0,
                        applied_vouchers=[]
                    )
                    msg = (
                        f"✅ <b>ĐÃ THIẾT LẬP MỤC TIÊU THEO DÕI!</b>\n\n"
                        f"📦 <b>{pending['name']}</b>\n"
                        f"🎯 <b>Giá muốn đạt được:</b> <b><u>≤ {int(target_price):,}đ</u></b>\n"
                        f"⏳ <b>Trạng thái:</b> Đang theo dõi voucher & đợt giảm giá...\n\n"
                        f"💡 <i>Bot sẽ bắn cảnh báo ngay khi phát hiện voucher giúp mua món này với giá ≤ {int(target_price):,}đ!</i>"
                    )
                    buttons = {
                        "inline_keyboard": [
                            [
                                {"text": "🎯 Đổi Giá Muốn Đạt", "callback_data": f"chtarget_{item_id}"},
                                {"text": "🛒 Xem Trên Shopee", "url": pending["url"]}
                            ],
                            [
                                {"text": "📋 Xem Watchlist", "callback_data": "menu_list"},
                                {"text": "❌ Hủy Canh", "callback_data": f"del_{item_id}"}
                            ]
                        ]
                    }
                    await self.send_message(msg, reply_markup=buttons)
                    return

        # 2. Kiểm tra dán link Shopee trực tiếp
        if "shopee.vn" in clean_text or "shp.ee" in clean_text:
            if not clean_text.startswith("/"):
                handled = await self.handle_direct_link(clean_text, user_chat_id=user_chat_id)
                if handled:
                    return

        parts = clean_text.split()
        cmd = parts[0].lower().split("@")[0]
        args = parts[1:]

        if cmd in ["/start", "/help", "/menu"]:
            await self._cmd_help()
        elif cmd in ["/hidden", "/maan", "/ma_an", "/an"]:
            await self._cmd_hidden_vouchers()
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
        elif cmd in ["/addvoucher", "/them_ma", "/ma"]:
            await self._cmd_add_voucher(args)
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
            "• Hệ thống <b>tự động bắn tin</b> khi có Mã Ẩn / Voucher HOT hoặc sản phẩm đạt giá.\n"
            "• Xem kho mã ẩn nhập tay: <code>/hidden</code>\n"
            "• Thêm mã giảm thủ công: <code>/addvoucher &lt;mã&gt; &lt;giảm&gt; [đơn_tt] [tên_shop]</code>\n\n"
            "👇 <b>Bấm các nút dưới đây để thao tác nhanh:</b>"
        )
        buttons = self.get_main_menu_keyboard()
        await self.send_message(msg, reply_markup=buttons)

    def get_main_menu_keyboard(self):
        return {
            "inline_keyboard": [
                [
                    {"text": "🔑 Kho Mã Ẩn", "callback_data": "menu_hidden"},
                    {"text": "🔥 Siêu Voucher HOT", "callback_data": "menu_hot"}
                ],
                [
                    {"text": "📋 Xem Watchlist", "callback_data": "menu_list"},
                    {"text": "➕ Thêm Sản Phẩm", "callback_data": "menu_add_guide"}
                ],
                [
                    {"text": "⚡️ Quét Deal & Mã Ẩn", "callback_data": "menu_check"},
                    {"text": "⚙️ Cài Đặt", "callback_data": "menu_settings"}
                ]
            ]
        }

    async def _cmd_add_guide(self):
        msg = (
            "➕ <b>CÁCH THÊM SẢN PHẨM CANH DEAL</b>\n\n"
            "Chỉ cần gửi <b>LINK</b> và <b>MỨC GIÁ BẠN MUỐN ĐẠT ĐƯỢC</b>:\n\n"
            "💡 <b>Ví dụ:</b>\n"
            "• Gửi kèm giá: <code>https://s.shopee.vn/4VdSGmu8Pf 100k</code>\n"
            "• Hoặc chỉ gửi link Shopee, bot sẽ hỏi bạn mức giá muốn mua!\n\n"
            "👉 <i>Dù sản phẩm có bao nhiêu phân loại đắt hay rẻ, bot sẽ bám sát duy nhất mức giá bạn đã đặt!</i>"
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
                "Bạn chưa thêm sản phẩm nào. Hãy copy và dán một link Shopee kèm giá mong muốn vào đây!"
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
            ready_icon = "🔥 ĐÃ ĐẠT GIÁ" if p.get("is_deal_ready") == 1 else "⏳ Đang theo dõi"
            t_mode = str(p.get('target_mode', 'PRICE')).upper()
            t_val = float(p.get('target_value', 0))
            t_str = f"giảm ≥ {t_val}%" if t_mode == 'PERCENT' else f"≤ {int(t_val):,}đ"
            
            msg += (
                f"{i}. <b>{p['name']}</b>\n"
                f"   • Trạng thái: <b>{ready_icon}</b>\n"
                f"   • Giá muốn đạt được: <b><u>{t_str}</u></b>\n"
                f"   • ID: <code>{p.get('item_id_on_platform') or p.get('item_id')}</code>\n\n"
            )

        kb_rows = []
        for p in products[:4]:
            i_id = p.get('item_id_on_platform') or p.get('item_id')
            short_name = p['name'][:12] + ".." if len(p['name']) > 12 else p['name']
            kb_rows.append([
                {"text": f"🎯 Đổi Giá: {short_name}", "callback_data": f"chtarget_{i_id}"},
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
        hidden_cnt = len(database.get_vouchers(hidden_only=True))
        msg = (
            f"✅ <b>ĐÃ HOÀN TẤT CHU KỲ QUÉT!</b>\n\n"
            f"• Số sản phẩm theo dõi: <b>{stats['total_products']} món</b>\n"
            f"• Số deal đạt mục tiêu mua: <b>{stats['ready_deals']} món</b>\n"
            f"• Mã ẩn nhập tay (Siêu Hội Shopee): <b>{hidden_cnt} mã</b>\n"
            f"• Kho voucher xịn đang mở: <b>{stats['total_vouchers']} mã</b>\n\n"
            f"🤖 <i>Bot sẽ tự động gửi cảnh báo khẩn khi có mã ẩn mới hoặc sản phẩm đạt giá.</i>"
        )
        buttons = {
            "inline_keyboard": [
                [
                    {"text": "🔑 Kho Mã Ẩn Nhập Tay", "callback_data": "menu_hidden"},
                    {"text": "🔥 Xem Voucher HOT", "callback_data": "menu_hot"}
                ],
                [
                    {"text": "📋 Xem Watchlist", "callback_data": "menu_list"},
                    {"text": "🏠 Menu Chính", "callback_data": "menu_home"}
                ]
            ]
        }
        await self.send_message(msg, reply_markup=buttons)

    async def _cmd_hidden_vouchers(self):
        """Liệt kê danh sách các mã ẩn độc quyền / Siêu Hội Shopee (chạm để copy)"""
        vouchers = database.get_vouchers(hidden_only=True)
        if not vouchers:
            await self.send_message("Hiện tại chưa có mã ẩn nào mới. Hãy bấm Quét Cập Nhật Mã.")
            return

        header = "🔑🔥 <b>KHO MÃ ẨN NHẬP TAY — SIÊU HỘI SHOPEE:</b>\n"
        header += "<i>(Chạm vào mã chữ in đậm để sao chép & dán vào ô Shopee Voucher)</i>\n\n"
        body = ""
        kb_rows = []

        for i, v in enumerate(vouchers[:10], 1):
            d_val = int(v['discount_value'])
            d_str = f"Giảm {int(v['discount_value'])}% (Tối đa {int(v['max_discount_amount']):,}đ)" if v['discount_type'] in ['PERCENT', 'PERCENTAGE'] else f"Giảm {d_val:,}đ"
            min_sp = f"đơn từ {int(v['min_spend']):,}đ" if v['min_spend'] > 0 else "đơn 0đ"
            code = v.get("voucher_code") or "LƯU BANNER"
            
            shop_scope = get_voucher_shop_scope(v)
            shop_str = f"   🏪 <i>Chỉ áp dụng: Shop {shop_scope}</i>\n" if shop_scope else ""
            cat_name = v.get("category") or "Siêu Hội Shopee"
            
            body += (
                f"{i}. 🔑 <code>{code}</code>\n"
                f"   💰 <b>{d_str}</b> (<b>{min_sp}</b>)\n"
                f"   📦 {cat_name}\n"
                f"{shop_str}\n"
            )

        body += "💡 <i>Mẹo: Vào giỏ hàng Shopee, dán mã vào ô 'Shopee Voucher' để nhận ưu đãi!</i>"

        kb_rows.append([
            {"text": "🛒 Mở Shopee Áp Mã Ngay", "url": "https://shopee.vn/m/ma-giam-gia"},
            {"text": "🔥 Siêu Voucher HOT", "callback_data": "menu_hot"}
        ])
        kb_rows.append([
            {"text": "⚡️ Quét Cập Nhật Mã", "callback_data": "menu_check"},
            {"text": "🏠 Menu Chính", "callback_data": "menu_home"}
        ])

        await self.send_message(header + body, reply_markup={"inline_keyboard": kb_rows})

    async def _cmd_vouchers(self, min_score: int = 0, hot_only: bool = False):
        vouchers = database.get_vouchers(hot_only=hot_only)
        if not vouchers:
            await self.send_message("Hiện tại chưa có mã giảm nào. Hãy bấm Quét Deal để cập nhật.")
            return

        header = "🔑 <b>DANH SÁCH MÃ GIẢM HOT & MÃ ẨN:</b>\n\n"
        body = ""
        kb_rows = []

        for i, v in enumerate(vouchers[:8], 1):
            d_val = int(v['discount_value'])
            d_str = f"Giảm {int(v['discount_value'])}% (Tối đa {int(v['max_discount_amount']):,}đ)" if v['discount_type'] in ['PERCENT', 'PERCENTAGE'] else f"Giảm {d_val:,}đ"
            min_sp = f"đơn từ {int(v['min_spend']):,}đ" if v['min_spend'] > 0 else "đơn 0đ"
            code = v.get("voucher_code") or "LƯU BANNER"
            is_hid = "🔑 [MÃ ẨN] " if v.get("is_hidden") == 1 else "🏷 "
            
            shop_scope = get_voucher_shop_scope(v)
            shop_str = f"   🏪 <i>Chỉ áp dụng: Shop {shop_scope}</i>\n" if shop_scope else ""
            
            body += (
                f"{i}. {is_hid}<code>{code}</code>\n"
                f"   💰 <b>{d_str}</b> ({min_sp})\n"
                f"   📦 {v.get('category') or 'Toàn sàn'}\n"
                f"{shop_str}\n"
            )

        body += "👉 <i>Chạm vào mã chữ in đậm để sao chép nhanh rồi dán vào giỏ hàng Shopee!</i>"

        kb_rows.append([
            {"text": "🛒 Mở Shopee Áp Mã", "url": "https://shopee.vn/m/ma-giam-gia"},
            {"text": "📋 Xem Watchlist", "callback_data": "menu_list"}
        ])
        kb_rows.append([
            {"text": "⚡️ Quét Cập Nhật Mã", "callback_data": "menu_check"},
            {"text": "🏠 Menu Chính", "callback_data": "menu_home"}
        ])

        await self.send_message(header + body, reply_markup={"inline_keyboard": kb_rows})

    async def _cmd_why(self, args: List[str]):
        if not args:
            await self.send_message("⚠️ Cú pháp: <code>/why &lt;voucher_code&gt;</code>")
            return
        v_id = args[0]
        voucher = database.get_voucher_by_id(v_id)
        if not voucher:
            await self.send_message(f"❌ Không tìm thấy voucher với mã <code>{v_id}</code>.")
            return

        code = voucher.get("voucher_code") or "LƯU BANNER"
        shop_scope = get_voucher_shop_scope(voucher)
        shop_line = f"• <b>Áp dụng:</b> Chỉ Shop {shop_scope}\n" if shop_scope else ""
        msg = (
            f"🏷 <b>MÃ GIẢM GIÁ:</b> <code>{code}</code> <i>(chạm để sao chép)</i>\n\n"
            f"• <b>Tên ưu đãi:</b> {voucher.get('title')}\n"
            f"• <b>Đơn tối thiểu:</b> {int(voucher.get('min_spend', 0)):,}đ\n"
            f"• <b>Phạm vi:</b> {voucher.get('category') or 'Toàn sàn'}\n"
            f"{shop_line}"
            f"• <b>Cách dùng:</b> {voucher.get('guide') or 'Nhập mã vào ô Shopee Voucher khi thanh toán.'}"
        )
        buttons = {
            "inline_keyboard": [
                [{"text": "🛒 Mở Shopee Áp Mã", "url": voucher.get("claim_url", "https://shopee.vn")}],
                [{"text": "📋 Xem Watchlist", "callback_data": "menu_list"}, {"text": "🏠 Menu Chính", "callback_data": "menu_home"}]
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

        shop_scope = get_voucher_shop_scope(shop_v) if shop_v else None
        shop_label = f" (Shop {shop_scope})" if shop_scope else ""

        msg = (
            f"🧮 <b>MÔ PHỎNG VOUCHER STACKING (GIÁ THỰC TRẢ)</b>\n\n"
            f"📦 <b>Sản phẩm:</b> {details.get('name')}\n"
            f"💵 <b>Giá gốc:</b> {int(res['original_price']):,}đ\n"
            f"➖ Giảm trực tiếp Shop: -{int(res['applied_breakdown']['shop_direct']):,}đ\n"
            f"➖ Voucher Shop{shop_label}: -{int(res['applied_breakdown']['shop_voucher']):,}đ\n"
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

    async def _cmd_add_voucher(self, args: List[str]):
        """
        Thêm mã giảm giá thủ công:
        Cú pháp:
        - Toàn ngành / Toàn sàn (không cần ghi shop): /addvoucher <MÃ> <MỨC_GIẢM> [ĐƠN_TỐI_THIỂU]
          Ví dụ: /addvoucher SALE100K 100k 400k
        - Chỉ cho 1 Shop: /addvoucher <MÃ> <MỨC_GIẢM> [ĐƠN_TỐI_THIỂU] [TÊN_SHOP]
          Ví dụ: /addvoucher YONEX50K 50k 300k Yonex Official Store
        """
        if len(args) < 2:
            guide = (
                "⚠️ <b>Cú pháp thêm mã giảm giá:</b>\n\n"
                "1. <b>Mã toàn ngành / toàn sàn:</b>\n"
                "<code>/addvoucher &lt;mã&gt; &lt;mức_giảm&gt; [đơn_tối_thiểu]</code>\n"
                "<i>Ví dụ: <code>/addvoucher SALE100K 100k 400k</code></i>\n\n"
                "2. <b>Mã chỉ áp dụng cho 1 Shop:</b>\n"
                "<code>/addvoucher &lt;mã&gt; &lt;mức_giảm&gt; [đơn_tối_thiểu] &lt;tên_shop&gt;</code>\n"
                "<i>Ví dụ: <code>/addvoucher YONEX50K 50k 300k Yonex Official Store</code></i>"
            )
            await self.send_message(guide)
            return

        code = args[0].strip().upper()
        raw_discount = args[1].strip()

        # Parse discount
        d_type = "FIXED_AMOUNT"
        max_discount = 0.0
        if "%" in raw_discount:
            d_type = "PERCENTAGE"
            m_pct = re.search(r'(\d+)', raw_discount)
            d_val = float(m_pct.group(1)) if m_pct else 15.0
            max_discount = d_val * 10000.0
        else:
            parsed_d = self._parse_price_from_text(raw_discount)
            d_val = parsed_d if parsed_d else 50000.0
            max_discount = d_val

        # Parse min spend & shop
        min_spend = 0.0
        shop_name = None
        if len(args) >= 3:
            parsed_min = self._parse_price_from_text(args[2])
            if parsed_min is not None:
                min_spend = parsed_min
                if len(args) >= 4:
                    shop_name = " ".join(args[3:]).strip()
            else:
                shop_name = " ".join(args[2:]).strip()

        # Xác định phạm vi áp dụng: nếu là toàn ngành / toàn sàn thì không ghi
        is_shop_voucher = False
        if shop_name:
            clean_shop = shop_name.lower().replace("shop", "").strip()
            if clean_shop in ["toàn sàn", "toàn ngành", "toan san", "toan nganh", "mọi shop", "all"]:
                shop_name = None
                v_type = "PLATFORM"
                cat = "Toàn sàn"
            else:
                is_shop_voucher = True
                v_type = "SHOP"
                cat = "Voucher Shop"
        else:
            v_type = "PLATFORM"
            cat = "Toàn sàn"

        v_data = {
            "voucher_id": f"USER_{code}",
            "voucher_id_on_platform": code,
            "voucher_code": code,
            "voucher_type": v_type,
            "category": cat,
            "title": f"Mã nhập: {code} (-{int(d_val)}{'%' if d_type == 'PERCENTAGE' else 'đ'})",
            "description": "Mã do người dùng thêm",
            "discount_type": d_type,
            "discount_value": d_val,
            "max_discount_amount": max_discount,
            "min_spend": min_spend,
            "shop_id": "0" if not is_shop_voucher else "USER_SHOP",
            "shop_name": shop_name,
            "claim_url": "https://shopee.vn/m/ma-giam-gia",
            "guide": f"Nhập mã {code} tại bước thanh toán.",
            "is_hidden": 1,
            "status": "ACTIVE"
        }

        database.upsert_voucher(v_data)

        d_str = f"Giảm {int(d_val)}%" if d_type == "PERCENTAGE" else f"Giảm {int(d_val):,}đ"
        min_str = f"Đơn từ {int(min_spend):,}đ" if min_spend > 0 else "Đơn từ 0đ"
        shop_info = f"\n🏪 <b>Áp dụng:</b> Chỉ Shop <b>{shop_name}</b>" if is_shop_voucher else "\n📦 <b>Phạm vi:</b> Toàn ngành / Toàn sàn"

        msg = (
            f"✅ <b>ĐÃ THÊM MÃ GIẢM GIÁ THÀNH CÔNG!</b>\n\n"
            f"🏷 <b>Mã:</b> <code>{code}</code> <i>(chạm để sao chép)</i>\n"
            f"💰 <b>Mức giảm:</b> <b>{d_str}</b>\n"
            f"🛒 <b>Điều kiện:</b> {min_str}"
            f"{shop_info}\n\n"
            f"💡 <i>Mã này đã được lưu vào kho và sẽ tự động đưa vào công thức tính gộp giá thực trả!</i>"
        )
        buttons = {
            "inline_keyboard": [
                [{"text": "🔑 Xem Danh Sách Mã", "callback_data": "menu_vouchers"}],
                [{"text": "⚡️ Quét Đối Soát Ngay", "callback_data": "menu_check"}]
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
                                elif cb_data == "menu_hidden":
                                    asyncio.create_task(self._cmd_hidden_vouchers())
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
                                elif cb_data.startswith("chtarget_"):
                                    item_id = cb_data.replace("chtarget_", "")
                                    p_exist = database.get_product_by_id(item_id)
                                    p_name = p_exist["name"] if p_exist else f"Sản phẩm {item_id}"
                                    self.pending_price_input[sender_id] = {
                                        "action": "update_target",
                                        "item_id": item_id
                                    }
                                    asyncio.create_task(self.send_message(
                                        f"🎯 <b>Nhập mức giá mới bạn muốn đạt được cho:</b>\n"
                                        f"📦 <i>{p_name}</i>\n\n"
                                        f"<i>(Chỉ cần gửi tin nhắn số tiền, ví dụ: <code>90k</code> hoặc <code>95000</code>)</i>"
                                    ))
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

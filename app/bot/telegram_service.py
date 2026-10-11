import asyncio
import os
import re
import uuid
import httpx
from datetime import datetime
from typing import Dict, Any, Optional, List

from config.settings import settings
from repositories.voucher_repository import VoucherRepository
from repositories.shop_repository import ShopRepository
from repositories.scan_repository import ScanRepository
from services.discovery_service import DiscoveryService
from services.dedupe_service import DedupeService
from services.lifecycle_service import LifecycleService
from models.voucher import Voucher, VoucherStatus, ScopeType
from models.notification import NotificationEvent, NotificationEventType
from app.bot.keyboard_factory import get_main_keyboard, get_voucher_action_keyboard, get_back_keyboard
from app.bot.scan_controls import ScanControls
from app.bot.elite_keyboard import get_elite_main_keyboard, get_elite_back_keyboard, get_elite_voucher_action_keyboard
from app.bot.elite_commands import EliteCommands
from services.elite_discovery_service import EliteDiscoveryService
from services.elite_notification_service import EliteNotificationService
from app.bot.notification_templates import (
    format_upcoming_known_code,
    format_upcoming_unknown_code,
    format_active_voucher,
    format_countdown_reminder,
    format_code_revealed,
    format_currency,
    format_discount_value
)

class TelegramBotService:
    def __init__(self, token: Optional[str] = None, chat_id: Optional[str] = None):
        self.token = token or settings.telegram_bot_token
        self.chat_id = str(chat_id or settings.telegram_chat_id)
        self.api_url = f"https://api.telegram.org/bot{self.token}"
        self.is_running = False
        self.last_update_id = 0

        # Khởi tạo các tầng repository & services
        self.voucher_repo = VoucherRepository()
        self.shop_repo = ShopRepository()
        self.scan_repo = ScanRepository()
        self.dedupe_service = DedupeService(self.scan_repo)
        self.discovery_service = DiscoveryService(self.voucher_repo, self.scan_repo)
        self.lifecycle_service = LifecycleService(self.voucher_repo, self.scan_repo, self.dedupe_service)
        self.scan_controls = ScanControls(self.voucher_repo, self.shop_repo, self.discovery_service)

        # Khởi tạo tầng Elite Radar
        self.elite_discovery = EliteDiscoveryService(self.voucher_repo, self.scan_repo, self.shop_repo)
        self.elite_commands = EliteCommands(self.voucher_repo, self.shop_repo, self.elite_discovery)
        self.elite_notifier = EliteNotificationService(self, self.scan_repo)

        # Trạng thái chờ người dùng nhập link shop
        self.awaiting_shop_link_users = set()
        self.pending_price_input: Dict[str, Dict[str, Any]] = {}

    def get_main_menu_keyboard(self) -> Dict[str, Any]:
        """Bàn phím chính 5 nút chuẩn Elite Radar"""
        return get_elite_main_keyboard()

    @staticmethod
    def _parse_price_from_text(text: str) -> Optional[float]:
        """Tương thích ngược: trích xuất giá từ text"""
        if not text:
            return None
        clean = text.lower().replace(" ", "").replace("đ", "").replace("vnd", "")
        m_tr = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:tr|trieu|m)', clean)
        if m_tr:
            try:
                return float(m_tr.group(1).replace(",", ".")) * 1_000_000
            except ValueError:
                pass
        m_k = re.search(r'(\d+(?:[.,]\d+)?)\s*k', clean)
        if m_k:
            try:
                return float(m_k.group(1).replace(",", ".")) * 1_000
            except ValueError:
                pass
        m_dots = re.search(r'(\d{1,3}(?:[.,]\d{3})+)', clean)
        if m_dots:
            raw_num = m_dots.group(1).replace(".", "").replace(",", "")
            try:
                return float(raw_num)
            except ValueError:
                pass
        m_dec = re.findall(r'(?:\b|[a-zA-Z])(\d{4,10}(?:\.\d+)?)\b', clean)
        if m_dec:
            try:
                return float(m_dec[0])
            except ValueError:
                pass

        m_pure = re.findall(r'\b\d{4,10}\b', clean)
        if m_pure:
            try:
                return float(m_pure[0])
            except ValueError:
                pass

        m_small = re.findall(r'\b\d{2,3}\b', clean)
        if m_small and (len(text.strip()) <= 5):
            try:
                val = float(m_small[0])
                if val <= 500:
                    return val * 1000
            except ValueError:
                pass
        return None

    async def _cmd_hidden_vouchers(self):
        """Tương thích ngược: lệnh xem kho mã ẩn"""
        from core import database
        vouchers = database.get_vouchers(hidden_only=True)
        lines = ["🔑 <b>KHO MÃ ẨN NHẬP TAY ĐỘC QUYỀN</b>\n"]
        for v in vouchers:
            code = v.get("voucher_code") or "CODE"
            lines.append(f"• <code>{code}</code>: {v.get('title')}")
        markup = {
            "inline_keyboard": [
                [{"text": "🛒 Mở Shopee Áp Mã", "url": "https://shopee.vn"}]
            ]
        }
        await self.send_message("\n".join(lines), reply_markup=markup)

    async def _cmd_add_voucher(self, args: List[str]):
        """Tương thích ngược: lệnh thêm voucher cũ"""
        from core import database
        if len(args) < 3:
            return
        code = args[0].upper()
        d_val = self._parse_price_from_text(args[1]) or 50000.0
        min_sp = self._parse_price_from_text(args[2]) or 0.0
        shop_name = " ".join(args[3:]) if len(args) > 3 else None
        vtype = "SHOP" if shop_name else "PLATFORM"
        v_data = {
            "voucher_id": code,
            "voucher_code": code,
            "title": f"Mã {'Shop ' + shop_name if shop_name else 'Toàn Sàn'}: Giảm {int(d_val):,}đ",
            "voucher_type": vtype,
            "discount_type": "FIXED_AMOUNT",
            "discount_value": d_val,
            "min_spend": min_sp,
            "shop_name": shop_name,
            "shop_id": shop_name.lower().replace(" ", "_") if shop_name else None,
            "claim_url": "https://shopee.vn",
            "is_freeship": 0,
            "status": "ACTIVE"
        }
        database.upsert_voucher(v_data)
        await self.send_message(f"✅ Đã thêm voucher <code>{code}</code> thành công.")

    async def handle_direct_link(self, text: str, user_chat_id: str = "default") -> bool:
        """Tương thích ngược: xử lý dán link sản phẩm cũ"""
        from app.connectors.shopee_connector import ShopeeConnector
        from core import database
        m = re.search(r'https?://[^\s]+', text)
        url_to_parse = m.group(0) if m else text
        parsed_link = await ShopeeConnector.resolve_url_and_parse(url_to_parse)
        if not parsed_link or not parsed_link.get("item_id"):
            return False
        price = self._parse_price_from_text(text)
        item_id = str(parsed_link["item_id"])
        shop_id = str(parsed_link.get("shop_id", ""))
        name = parsed_link.get("name") or "Sản phẩm Shopee"
        image_url = parsed_link.get("image_url") or "https://shopee.vn/logo.png"
        database.add_product(
            item_id=item_id,
            shop_id=shop_id,
            name=name,
            url=url_to_parse,
            image_url=image_url,
            target_mode="PRICE" if price else "PERCENT",
            target_value=price if price else 30.0,
            baseline_price=100000.0
        )
        await self.send_photo(image_url, f"Đã lưu sản phẩm {name}")
        return True

    async def handle_command(self, text: str, user_chat_id: str = "default") -> None:
        """Tương thích ngược: router lệnh cũ"""
        if "shopee.vn" in text and ("/product/" in text or "-i." in text or "s.shopee.vn" in text):
            self.pending_price_input[user_chat_id] = {"link": text}
            await self.send_message("Vui lòng nhập giá mong muốn:")
        elif user_chat_id in self.pending_price_input:
            p_data = self.pending_price_input.pop(user_chat_id)
            await self.handle_direct_link(f"{p_data['link']} {text}", user_chat_id=user_chat_id)
        else:
            await self.handle_message({"text": text, "chat": {"id": user_chat_id}})


    async def send_message(self, text: str, reply_markup=None, parse_mode="HTML") -> Optional[Dict[str, Any]]:
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": False
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.post(f"{self.api_url}/sendMessage", json=payload)
                return res.json()
            except Exception as e:
                print(f"[Telegram] Lỗi gửi tin nhắn: {e}")
                return None

    async def answer_callback(self, callback_query_id: str, text: Optional[str] = None) -> None:
        try:
            payload = {"callback_query_id": callback_query_id}
            if text:
                payload["text"] = text
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.post(f"{self.api_url}/answerCallbackQuery", json=payload)
        except Exception:
            pass

    # ----------------- HÀM GỬI CẢNH BÁO TỚI TELEGRAM (ZERO DUPLICATE) -----------------

    async def broadcast_upcoming_voucher(self, voucher: Voucher) -> bool:
        """Gửi cảnh báo mã sắp mở hoặc sự kiện chưa có code"""
        if voucher.voucher_code:
            text = format_upcoming_known_code(voucher)
            ev_type = NotificationEventType.NEW_CODE
        else:
            text = format_upcoming_unknown_code(voucher)
            ev_type = NotificationEventType.EVENT_UPCOMING

        fp = self.dedupe_service.calculate_fingerprint(voucher, ev_type.value)
        if self.dedupe_service.is_duplicate(fp):
            return False

        markup = get_voucher_action_keyboard(voucher.source_url)
        res = await self.send_message(text, reply_markup=markup)
        msg_id = res.get("result", {}).get("message_id") if res else None

        self.scan_repo.record_notification(NotificationEvent(
            id=f"NOTIF_{uuid.uuid4().hex[:8]}",
            voucher_id=voucher.id,
            event_type=ev_type,
            content_fingerprint=fp,
            telegram_message_id=msg_id
        ))
        return True

    async def broadcast_active_voucher(self, voucher: Voucher) -> bool:
        """Gửi cảnh báo mã vừa mở (ACTIVE)"""
        fp = self.dedupe_service.calculate_fingerprint(voucher, "ACTIVE_NOW")
        if self.dedupe_service.is_duplicate(fp):
            return False

        text = format_active_voucher(voucher)
        markup = get_voucher_action_keyboard(voucher.source_url)
        res = await self.send_message(text, reply_markup=markup)
        msg_id = res.get("result", {}).get("message_id") if res else None

        self.scan_repo.record_notification(NotificationEvent(
            id=f"NOTIF_{uuid.uuid4().hex[:8]}",
            voucher_id=voucher.id,
            event_type=NotificationEventType.VOUCHER_OPENED,
            content_fingerprint=fp,
            telegram_message_id=msg_id
        ))
        return True

    async def broadcast_reminder(self, voucher: Voucher, reminder_type: str) -> bool:
        """Gửi thông báo nhắc giờ T-60m / T-15m / T-5m / T-2m"""
        fp = self.dedupe_service.calculate_fingerprint(voucher, reminder_type)
        if self.dedupe_service.is_duplicate(fp):
            return False

        text = format_countdown_reminder(voucher, reminder_type)
        markup = get_voucher_action_keyboard(voucher.source_url)
        res = await self.send_message(text, reply_markup=markup)
        msg_id = res.get("result", {}).get("message_id") if res else None

        ev_map = {
            "REMINDER_60M": NotificationEventType.REMINDER_60M,
            "REMINDER_15M": NotificationEventType.REMINDER_15M,
            "REMINDER_5M": NotificationEventType.REMINDER_5M,
            "REMINDER_2M": NotificationEventType.REMINDER_2M,
        }
        # Fallback cho DB cũ chưa có enum mới
        try:
            ev_enum = ev_map.get(reminder_type, NotificationEventType.REMINDER_15M)
        except Exception:
            ev_enum = NotificationEventType.REMINDER_15M
        self.scan_repo.record_notification(NotificationEvent(
            id=f"NOTIF_{uuid.uuid4().hex[:8]}",
            voucher_id=voucher.id,
            event_type=ev_enum,
            content_fingerprint=fp,
            telegram_message_id=msg_id
        ))
        return True

    async def broadcast_code_revealed(self, voucher: Voucher) -> bool:
        """Gửi thông báo sự kiện vừa công bố code chính thức"""
        fp = self.dedupe_service.calculate_fingerprint(voucher, "CODE_REVEALED")
        if self.dedupe_service.is_duplicate(fp):
            return False

        text = format_code_revealed(voucher)
        markup = get_voucher_action_keyboard(voucher.source_url)
        res = await self.send_message(text, reply_markup=markup)
        msg_id = res.get("result", {}).get("message_id") if res else None

        self.scan_repo.record_notification(NotificationEvent(
            id=f"NOTIF_{uuid.uuid4().hex[:8]}",
            voucher_id=voucher.id,
            event_type=NotificationEventType.CODE_REVEALED,
            content_fingerprint=fp,
            telegram_message_id=msg_id
        ))
        return True

    # ----------------- XỬ LÝ LỆNH & NÚT BẤM (BOT CONTROLS) -----------------

    def get_welcome_message(self) -> str:
        return self.elite_commands.get_welcome_message()

    async def handle_callback_query(self, query: Dict[str, Any]) -> None:
        query_id = query.get("id")
        data = query.get("data", "")
        message = query.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", self.chat_id))

        await self.answer_callback(query_id)

        # Bộ điều hướng Elite Radar
        if data in ("action:elite_menu", "action:menu"):
            await self.send_message(self.get_welcome_message(), reply_markup=get_elite_main_keyboard())
        elif data in ("action:elite_super", "action:top"):
            msg, markup = await self.elite_commands.handle_super_vouchers()
            await self.send_message(msg, reply_markup=markup)
        elif data in ("action:elite_upcoming", "action:upcoming"):
            msg, markup = await self.elite_commands.handle_upcoming_vouchers()
            await self.send_message(msg, reply_markup=markup)
        elif data in ("action:elite_shops", "action:shops"):
            msg, markup = await self.elite_commands.handle_shop_vouchers()
            await self.send_message(msg, reply_markup=markup)
        elif data in ("action:elite_scan_now", "action:scan_now"):
            msg, markup = await self.elite_commands.handle_scan_now()
            await self.send_message(msg, reply_markup=markup)
        elif data in ("action:elite_settings", "action:settings"):
            msg, markup = self.elite_commands.get_settings_view()
            await self.send_message(msg, reply_markup=markup)
        elif data == "action:platform":
            msg, markup = self.scan_controls.get_platform_view()
            await self.send_message(msg, reply_markup=markup)
        elif data == "action:add_shop":
            self.awaiting_shop_link_users.add(chat_id)
            prompt = (
                "➕ <b>THÊM SHOP VÀO DANH SÁCH THEO DÕI</b>\n\n"
                "Vui lòng dán link shop Shopee công khai vào đây\n"
                "<i>(Ví dụ: https://shopee.vn/ten_shop hoặc /addshop https://shopee.vn/ten_shop)</i>:"
            )
            await self.send_message(prompt, reply_markup=get_elite_back_keyboard())

    async def handle_message(self, message: Dict[str, Any]) -> None:
        chat_id = str(message.get("chat", {}).get("id", self.chat_id))
        text = str(message.get("text", "")).strip()
        if not text:
            return

        # 1. Các lệnh bắt đầu / điều hướng chính
        if text in ("/start", "/help", "/menu"):
            await self.send_message(self.get_welcome_message(), reply_markup=get_elite_main_keyboard())
            return

        if text in ("/scan", "/quyetngay"):
            msg, markup = await self.elite_commands.handle_scan_now()
            await self.send_message(msg, reply_markup=markup)
            return

        if text in ("/upcoming", "/sapmo"):
            msg, markup = await self.elite_commands.handle_upcoming_vouchers()
            await self.send_message(msg, reply_markup=markup)
            return

        if text in ("/shops", "/mashop"):
            msg, markup = await self.elite_commands.handle_shop_vouchers()
            await self.send_message(msg, reply_markup=markup)
            return

        if text in ("/elite", "/super", "/top"):
            msg, markup = await self.elite_commands.handle_super_vouchers()
            await self.send_message(msg, reply_markup=markup)
            return

        if text.startswith("/addshop"):
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                res_msg, _ = self.scan_controls.parse_and_add_shop(parts[1])
                await self.send_message(res_msg, reply_markup=get_elite_main_keyboard())
            else:
                self.awaiting_shop_link_users.add(chat_id)
                await self.send_message("Vui lòng gửi link shop dạng: <code>/addshop https://shopee.vn/ten_shop</code>", reply_markup=get_elite_back_keyboard())
            return

        if text.startswith("/removeshop"):
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                res_msg = self.scan_controls.remove_shop(parts[1])
                await self.send_message(res_msg, reply_markup=get_elite_main_keyboard())
            else:
                await self.send_message("Vui lòng gửi mã shop cần xóa dạng: <code>/removeshop ten_shop</code>")
            return

        if text == "/active":
            active_list = self.voucher_repo.get_active_vouchers()
            if not active_list:
                await self.send_message("🟢 <i>Hiện không có mã nào đang ACTIVE trong hệ thống.</i>", reply_markup=get_elite_back_keyboard())
            else:
                lines = [f"🟢 <b>CÁC MÃ ĐANG HOẠT ĐỘNG ({len(active_list)} mã):</b>\n"]
                for v in active_list[:6]:
                    lines.append(f"• <code>{v.voucher_code}</code>: Giảm {format_discount_value(v)} (Đơn {format_currency(v.min_order_value)}) — Hạn {v.end_time}")
                await self.send_message("\n".join(lines), reply_markup=get_elite_back_keyboard())
            return

        if text == "/settings":
            msg, markup = self.elite_commands.get_settings_view()
            await self.send_message(msg, reply_markup=markup)
            return

        if text == "/status":
            personal_msg = self.elite_discovery.personal_source.get_status_message()
            status_msg = (
                "📊 <b>TRẠNG THÁI ELITE SHOPEE RADAR</b>\n"
                "────────────────────\n"
                "• Chế độ: <b>ELITE VOUCHER RADAR (Ngưỡng >= 80đ)</b>\n"
                "• Lọc Freeship: <b>KÍCH HOẠT (100% Loại trừ)</b>\n"
                f"• {personal_msg}\n"
            )
            await self.send_message(status_msg, reply_markup=get_elite_main_keyboard())
        if text.startswith("/leak") or text.startswith("/nhapma"):
            resp_msg = await self.elite_commands.handle_leak_command(text)
            await self.send_message(resp_msg, reply_markup=get_elite_main_keyboard())
            return

        if text == "/top" or text.startswith("/top "):
            try:
                from core.voucher_filter import score_voucher, is_super_voucher
                active = self.voucher_repo.get_active_vouchers()
                upcoming = self.voucher_repo.get_upcoming_vouchers(days=7)
                pool = list(active) + [v for v in upcoming if v.voucher_code]
                ranked = sorted(pool, key=lambda v: score_voucher(v), reverse=True)[:10]
                if not ranked:
                    await self.send_message("💎 <i>Chưa có mã ngon nào. Bấm Quét ngay để nạp.</i>", reply_markup=get_back_keyboard())
                else:
                    lines = ["💎 <b>TOP MÃ NGON NHẤT (0đ / rẻ lên trước):</b>\n"]
                    for v in ranked:
                        sc = score_voucher(v)
                        sup, _ = is_super_voucher(v)
                        star = "💎 " if sup else "• "
                        code = v.voucher_code or "CHƯA LỘ"
                        lines.append(f"{star}<code>{code}</code> {format_discount_value(v)} đơn {format_currency(v.min_order_value)} [{sc}đ] — {v.end_time}")
                    lines.append("\n✋ <i>Nhập tay thủ công, bot không tự claim.</i>")
                    await self.send_message("\n".join(lines), reply_markup=get_back_keyboard())
            except Exception as e:
                await self.send_message(f"Lỗi /top: {e}")
            return

        if text.startswith("/leak"):
            parts = text.split()
            if len(parts) < 2:
                await self.send_message(
                    "📥 <b>THÊM MÃ LEAK THỦ CÔNG</b>\n"
                    "Cú pháp: <code>/leak MÃCODE 100k 0</code>\n"
                    "VD: <code>/leak SIEUHOI100K 100000 0</code>\n"
                    "Bot chỉ đưa vào radar để nhắc giờ, không tự claim.",
                    reply_markup=get_back_keyboard())
                return
            code = parts[1].upper()
            d_val = self._parse_price_from_text(parts[2]) if len(parts) > 2 else 50000.0
            min_o = self._parse_price_from_text(parts[3]) if len(parts) > 3 else 0.0
            try:
                import json as _json
                inbox = os.path.join(os.getcwd(), "data", "leak_inbox.json")
                if not os.path.exists(os.path.dirname(inbox)):
                    inbox = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "leak_inbox.json")
                os.makedirs(os.path.dirname(inbox), exist_ok=True)
                rows = []
                if os.path.exists(inbox):
                    try:
                        with open(inbox, "r", encoding="utf-8") as f:
                            rows = _json.load(f) or []
                    except Exception:
                        rows = []
                rows.append({"code": code, "discount": d_val, "min_order": min_o, "title": f"Leak thủ công: {code}"})
                with open(inbox, "w", encoding="utf-8") as f:
                    _json.dump(rows, f, ensure_ascii=False, indent=2)
                await self.send_message(f"✅ Đã nạp <code>{code}</code> ({int(d_val):,}đ đơn {int(min_o):,}đ) vào radar. Bấm /scan để lên sóng.", reply_markup=get_main_keyboard())
            except Exception as e:
                await self.send_message(f"Lỗi lưu leak: {e}")
            return

        if text == "/xepchong":
            await self.send_message(
                "🧩 <b>CÁCH XẾP CHỒNG 3 LỚP RA 0đ (1 acc):</b>\n"
                "1. Mã sàn 100k/50k (từ /top)\n"
                "2. Mã Live/Video 30% (lưu trong live)\n"
                "3. Mã thanh toán ShopeePay/SPayLater\n"
                "Add hàng 1k-10k vào giỏ trước, tới giờ bot nhắc T-2m thì áp cả 3 lớp + xu.\n"
                "✋ <i>Lưu tay từng mã, không dùng tool claim hộ.</i>",
                reply_markup=get_back_keyboard())
            return

        # 2. Xử lý khi người dùng dán link shop Shopee trực tiếp
        if ("shopee.vn" in text and "/product/" not in text and "-i." not in text) or (chat_id in self.awaiting_shop_link_users):
            if chat_id in self.awaiting_shop_link_users:
                self.awaiting_shop_link_users.remove(chat_id)
            res_msg, _ = self.scan_controls.parse_and_add_shop(text)
            await self.send_message(res_msg, reply_markup=get_main_keyboard())
            return

        # 3. Mặc định phản hồi hướng dẫn
        fallback = (
            "💡 Tôi là <b>Shopee Voucher Radar</b> chuyên theo dõi mã sắp mở và mã ẩn.\n"
            "• Gửi link shop công khai để thêm vào theo dõi.\n"
            "• Bấm nút <b>Quét ngay</b> hoặc <b>Mã sắp mở</b> bên dưới để xem kho mã!"
        )
        await self.send_message(fallback, reply_markup=get_main_keyboard())

    async def start_polling(self) -> None:
        """Vòng lặp lắng nghe tin nhắn và callback từ Telegram"""
        self.is_running = True
        print(f"[Telegram Radar] Đã kết nối bot token {self.token[:8]}***. Bắt đầu polling...")

        async with httpx.AsyncClient(timeout=35.0) as client:
            while self.is_running:
                try:
                    params = {
                        "offset": self.last_update_id + 1,
                        "timeout": 20
                    }
                    res = await client.get(f"{self.api_url}/getUpdates", params=params)
                    if res.status_code == 200:
                        data = res.json()
                        for update in data.get("result", []):
                            self.last_update_id = update["update_id"]
                            if "callback_query" in update:
                                await self.handle_callback_query(update["callback_query"])
                            elif "message" in update:
                                await self.handle_message(update["message"])
                    await asyncio.sleep(0.5)
                except Exception as e:
                    await asyncio.sleep(3.0)

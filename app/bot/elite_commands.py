from typing import Tuple, Dict, Any, List, Optional
from models.voucher import Voucher, ScopeType, VerificationStatus, VoucherStatus
from repositories.voucher_repository import VoucherRepository
from repositories.shop_repository import ShopRepository
from services.elite_discovery_service import EliteDiscoveryService
from core.elite_score_calculator import calculate_elite_score, parse_vietnam_dt
from app.bot.elite_keyboard import (
    get_elite_main_keyboard,
    get_elite_back_keyboard,
    get_elite_voucher_action_keyboard
)
from app.bot.elite_templates import (
    format_scan_summary_elite,
    format_discount_display,
    format_currency,
    format_verified_active_voucher,
    format_verified_upcoming_voucher,
    format_upcoming_unknown_event,
    format_voucher_verification_card,
    format_voucher_source_card,
    format_voucher_status_card,
    format_audit_summary_report,
    format_coverage_report
)

class EliteCommands:
    def __init__(
        self,
        voucher_repo: VoucherRepository,
        shop_repo: ShopRepository,
        discovery_service: EliteDiscoveryService
    ):
        self.voucher_repo = voucher_repo
        self.shop_repo = shop_repo
        self.discovery_service = discovery_service
        self.settings = {
            "min_fixed_discount": 30000.0,
            "min_percent_rate": 30.0,
            "min_elite_score": 80,
            "reminder_15m": True,
            "reminder_2m": True,
            "platform_vouchers": True,
            "shop_vouchers": True,
            "new_user_vouchers": False,
            "lookahead_days": 7
        }

    def get_welcome_message(self) -> str:
        return (
            "📡 <b>ELITE SHOPEE VOUCHER RADAR</b>\n"
            "────────────────────\n"
            "Hệ thống săn mã Shopee giá trị thực sự cho cá nhân:\n"
            "• 🔥 <b>Chỉ báo mã đạt chuẩn Elite (>= 80/100 điểm)</b>\n"
            "• 🛡️ <b>100% Xác minh nguồn gốc & bằng chứng thời gian</b>\n"
            "• 💎 <b>Giảm từ 30k đơn 0đ hoặc từ 50k tỷ lệ vàng</b>\n"
            "• ⚡ <b>Giảm từ 30%, trần tối thiểu 50k</b>\n"
            "• 🚫 <b>TUYỆT ĐỐI KHÔNG FREESHIP & KHÔNG MÃ ẢO</b>\n\n"
            "Chọn chức năng bên dưới để bắt đầu:"
        )

    async def handle_super_vouchers(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý nút: 🔥 Mã siêu xịn (Chỉ hiển thị mã đã xác minh VERIFIED_ACTIVE/UPCOMING)"""
        verified_vouchers = self.voucher_repo.get_elite_verified_vouchers(limit=20)
        super_list = []
        worthy_list = []

        for v in verified_vouchers:
            score, label, _ = calculate_elite_score(v)
            if score >= 90:
                super_list.append((v, score))
            elif score >= 80:
                worthy_list.append((v, score))

        super_list.sort(key=lambda x: x[1], reverse=True)
        worthy_list.sort(key=lambda x: x[1], reverse=True)

        lines = ["💎 <b>DANH SÁCH VOUCHER ELITE ĐÃ XÁC MINH (>= 80 ĐIỂM)</b>\n"]

        if super_list:
            lines.append("🔥 <b>SIÊU XỊN (90–100 điểm):</b>")
            for v, sc in super_list[:5]:
                code = v.voucher_code
                vs = v.verification_status.value if isinstance(v.verification_status, VerificationStatus) else v.verification_status
                lines.append(f"• <code>{code}</code>: Giảm {format_discount_display(v)} (Đơn {format_currency(v.min_order_value)}) [{sc}đ] — <i>{vs}</i>")
            lines.append("")

        if worthy_list:
            lines.append("✅ <b>ĐÁNG LẤY (80–89 điểm):</b>")
            for v, sc in worthy_list[:5]:
                code = v.voucher_code
                vs = v.verification_status.value if isinstance(v.verification_status, VerificationStatus) else v.verification_status
                lines.append(f"• <code>{code}</code>: Giảm {format_discount_display(v)} (Đơn {format_currency(v.min_order_value)}) [{sc}đ] — <i>{vs}</i>")
            lines.append("")

        if not super_list and not worthy_list:
            lines.append("<i>Hiện tại chưa có mã nào đạt chuẩn xác minh VERIFIED_ACTIVE/UPCOMING (>= 80 điểm). Bấm '🔍 Quét ngay' để kiểm tra!</i>")

        return "\n".join(lines), get_elite_back_keyboard()

    async def handle_upcoming_vouchers(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý nút: 📅 Sắp mở (Phân biệt mã sắp mở đã xác minh và sự kiện đang theo dõi)"""
        verified_upcoming = [
            v for v in self.voucher_repo.get_elite_verified_vouchers(limit=20)
            if v.verification_status == VerificationStatus.VERIFIED_UPCOMING
        ]
        
        all_upcoming = self.voucher_repo.get_upcoming_vouchers(days=self.settings["lookahead_days"])
        events = [v for v in all_upcoming if v.verification_status == VerificationStatus.UPCOMING_UNKNOWN_CODE or not v.voucher_code]

        lines = [f"📅 <b>LỊCH SĂN VOUCHER ({self.settings['lookahead_days']} NGÀY TỚI)</b>\n"]

        if verified_upcoming:
            lines.append("🔑 <b>VOUCHER ELITE SẮP MỞ (ĐÃ XÁC MINH CODE):</b>")
            for v in verified_upcoming[:5]:
                score, _, _ = calculate_elite_score(v)
                lines.append(f"• <code>{v.voucher_code}</code>: Giảm {format_discount_display(v)} (Đơn {format_currency(v.min_order_value)})\n  ⏰ <i>Mở: {v.start_time}</i>")
            lines.append("")

        if events:
            lines.append("📅 <b>SỰ KIỆN ĐANG THEO DÕI (CHƯA CÔNG BỐ MÃ):</b>")
            for ev in events[:5]:
                lines.append(f"• <b>{ev.title}</b>\n  ⏰ <i>Dự kiến: {ev.start_time}</i> | Giảm {format_discount_display(ev)} (Đơn {format_currency(ev.min_order_value)})")
            lines.append("")

        if not verified_upcoming and not events:
            lines.append("<i>Chưa có voucher sắp mở hoặc sự kiện nào trong 7 ngày tới.</i>")

        return "\n".join(lines), get_elite_back_keyboard()

    async def handle_shop_vouchers(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý nút: 🏪 Mã shop (Chỉ hiện voucher Elite đã xác minh của shop được theo dõi)"""
        tracked = self.shop_repo.get_tracked_shops(enabled_only=True)
        tracked_ids = {str(s.shop_id).lower() for s in tracked} | {str(s.shop_name).lower() for s in tracked if s.shop_name}

        verified_all = self.voucher_repo.get_elite_verified_vouchers(limit=50)
        shop_vouchers = []

        for v in verified_all:
            if v.scope_type == ScopeType.SHOP or v.shop_id:
                s_id = str(v.shop_id or "").lower()
                s_name = str(v.shop_name or "").lower()
                if (s_id in tracked_ids) or (s_name in tracked_ids):
                    score, _, _ = calculate_elite_score(v, is_tracked_shop=True)
                    if score >= self.settings["min_elite_score"]:
                        shop_vouchers.append((v, score))

        shop_vouchers.sort(key=lambda x: x[1], reverse=True)

        lines = ["🏪 <b>MÃ SHOP ĐƯỢC THEO DÕI (ĐÃ XÁC MINH)</b>\n"]
        if not tracked:
            lines.append("<i>Bạn chưa theo dõi shop nào. Hãy gửi link shop để thêm vào radar!</i>")
        elif not shop_vouchers:
            lines.append("<i>Các shop bạn theo dõi hiện chưa có mã nào đạt chuẩn xác minh Elite (>= 80đ).</i>")
        else:
            for v, sc in shop_vouchers[:8]:
                code = v.voucher_code or "CHƯA LỘ"
                sname = v.shop_name or "Shop"
                lines.append(f"• <b>{sname}</b>: <code>{code}</code> Giảm {format_discount_display(v)} (Đơn {format_currency(v.min_order_value)}) [{sc}đ]")

        return "\n".join(lines), get_elite_back_keyboard()

    async def handle_scan_now(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý nút: 🔍 Quét ngay"""
        res = await self.discovery_service.run_elite_scan(min_elite_score=self.settings["min_elite_score"])
        msg = format_scan_summary_elite(
            sources_count=res["sources_count"],
            items_scanned=res["items_scanned"],
            items_rejected=res["items_rejected"],
            elite_new=res["elite_new"],
            elite_updated=res["elite_updated"],
            elite_upcoming=res["elite_upcoming"]
        )
        return msg, get_elite_back_keyboard()

    def get_settings_view(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý nút: ⚙️ Cài đặt"""
        st = self.settings
        msg = (
            "⚙️ <b>CẤU HÌNH BỘ LỌC ELITE SHOPEE RADAR</b>\n"
            "────────────────────\n"
            f"• Giảm tiền tối thiểu: <b>{int(st['min_fixed_discount']):,}đ</b>\n"
            f"• Phần trăm giảm tối thiểu: <b>{st['min_percent_rate']}%</b>\n"
            f"• Điểm Elite tối thiểu: <b>{st['min_elite_score']} điểm</b>\n"
            f"• Nhắc nhở T-15 phút: <b>{'BẬT' if st['reminder_15m'] else 'TẮT'}</b>\n"
            f"• Nhắc nhở T-2 phút: <b>{'BẬT' if st['reminder_2m'] else 'TẮT'}</b>\n"
            f"• Mã toàn sàn: <b>{'BẬT' if st['platform_vouchers'] else 'TẮT'}</b>\n"
            f"• Mã shop theo dõi: <b>{'BẬT' if st['shop_vouchers'] else 'TẮT'}</b>\n"
            f"• Voucher người dùng mới: <b>{'BẬT' if st['new_user_vouchers'] else 'TẮT'}</b>\n"
            f"• Số ngày xem trước: <b>{st['lookahead_days']} ngày</b>\n"
            "────────────────────\n"
            "🚫 <i>Bộ lọc Freeship luôn được BẬT ở mức 100% (không thể tắt).</i>"
        )
        return msg, get_elite_back_keyboard()

    async def handle_verify_command(self, text: str) -> str:
        """Xử lý lệnh: /verify <voucher_code>"""
        parts = text.strip().split()
        if len(parts) < 2:
            return "ℹ️ Cú pháp: <code>/verify &lt;MÃ_VOUCHER&gt;</code>\nVí dụ: <code>/verify PCU35ELHA</code>"
        code = parts[1].strip()
        v = self.voucher_repo.get_by_code(code) or self.voucher_repo.get_by_id(code)
        if not v:
            return f"❌ Không tìm thấy voucher với mã hoặc ID <code>{code}</code> trong hệ thống."
        return format_voucher_verification_card(v)

    async def handle_source_command(self, text: str) -> str:
        """Xử lý lệnh: /source <voucher_code>"""
        parts = text.strip().split()
        if len(parts) < 2:
            return "ℹ️ Cú pháp: <code>/source &lt;MÃ_VOUCHER&gt;</code>\nVí dụ: <code>/source PCU35ELHA</code>"
        code = parts[1].strip()
        v = self.voucher_repo.get_by_code(code) or self.voucher_repo.get_by_id(code)
        if not v:
            return f"❌ Không tìm thấy voucher với mã hoặc ID <code>{code}</code>."
        return format_voucher_source_card(v)

    async def handle_status_command(self, text: str) -> str:
        """Xử lý lệnh: /status [voucher_code]"""
        parts = text.strip().split()
        if len(parts) >= 2:
            code = parts[1].strip()
            v = self.voucher_repo.get_by_code(code) or self.voucher_repo.get_by_id(code)
            if not v:
                return f"❌ Không tìm thấy voucher <code>{code}</code>."
            return format_voucher_status_card(v)
        
        # /status chung
        import os
        cookie_status = "✅ ĐÃ KẾT NỐI (Chống 403 active)" if os.environ.get("SHOPEE_COOKIE") else "⚠️ Chưa cấu hình"
        personal_msg = self.discovery_service.personal_source.get_status_message()
        return (
            "📊 <b>TRẠNG THÁI ELITE SHOPEE RADAR</b>\n"
            "────────────────────\n"
            "• Chế độ: <b>ELITE VOUCHER RADAR (Ngưỡng >= 80đ)</b>\n"
            "• Tiêu chuẩn: <b>Chỉ chấp nhận mã có bằng chứng VERIFIED</b>\n"
            f"• Cookie Shopee: <b>{cookie_status}</b>\n"
            "• Lọc Freeship: <b>KÍCH HOẠT (100% Loại trừ)</b>\n"
            f"• {personal_msg}\n\n"
            "💡 <i>Gõ <code>/status &lt;MÃ&gt;</code> để kiểm tra trạng thái của một voucher cụ thể hoặc <code>/coverage</code> để xem độ bao phủ.</i>"
        )

    async def handle_coverage_command(self) -> str:
        """Xử lý lệnh: /coverage (Xem độ bao phủ dữ liệu và sức khỏe từng nguồn)"""
        import os
        cookie_enabled = bool(os.environ.get("SHOPEE_COOKIE"))
        tracked = self.shop_repo.get_tracked_shops(enabled_only=True)
        health_summary = self.voucher_repo.get_source_health_summary() if hasattr(self.voucher_repo, "get_source_health_summary") else {}
        stats = {
            "cookie_enabled": cookie_enabled,
            "tracked_count": len(tracked),
            "sources": health_summary
        }
        return format_coverage_report(stats, tracked_count=len(tracked))

    async def handle_elite_command(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý lệnh: /elite (Chỉ hiển thị các mã đã xác minh)"""
        return await self.handle_super_vouchers()

    async def handle_unverified_command(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý lệnh: /unverified (Xem các mã đang chờ kiểm tra)"""
        unverified = self.voucher_repo.get_unverified_vouchers(limit=15)
        lines = [
            "⚠️ <b>DANH SÁCH MÃ CHỜ KIỂM TRA (UNVERIFIED)</b>\n",
            "<i>Các mã dưới đây được phát hiện từ bài viết cộng đồng nhưng CHƯA CÓ BẰNG CHỨNG ngày giờ hoặc hạn mức chính thức từ Shopee. Bot KHÔNG gửi cảnh báo tự động cho các mã này.</i>\n"
        ]
        if not unverified:
            lines.append("<i>Hiện tại không có mã nào đang chờ kiểm tra.</i>")
        else:
            for v in unverified:
                code = v.voucher_code or v.id
                lines.append(f"• <code>{code}</code>: {v.title}\n  🔎 <i>Trích dẫn: {v.source_evidence_excerpt[:80]}...</i>")

        return "\n".join(lines), get_elite_back_keyboard()

    async def handle_audit_command(self) -> str:
        """Xử lý lệnh: /audit (Tóm tắt kiểm toán toàn diện)"""
        summary = self.voucher_repo.get_verification_audit_summary()
        return format_audit_summary_report(summary)

    async def handle_leak_command(self, text: str) -> str:
        """Thông báo tính năng /leak đã được loại bỏ"""
        return (
            "🤖 <b>TÍNH NĂNG /leak ĐÃ ĐƯỢC LOẠI BỎ</b>\n\n"
            "Bạn không cần phải tự đi tìm hay nạp mã thủ công nữa!\n"
            "Hệ thống <b>Elite Shopee Radar</b> tự động cào và giải mã các mã thật "
            "từ hệ sinh thái Shopee, lọc sạch 100% mã rác và freeship.\n\n"
            "👉 Hãy bấm <b>🔍 Quét ngay</b> hoặc <b>🔥 Mã siêu xịn</b> trên menu để nhận mã tự động!"
        )

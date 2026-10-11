from typing import Tuple, Dict, Any, List
from models.voucher import Voucher, ScopeType
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
    format_currency
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
            "• 💎 <b>Giảm từ 30k đơn 0đ hoặc từ 50k tỷ lệ vàng</b>\n"
            "• ⚡ <b>Giảm từ 30%, trần tối thiểu 50k</b>\n"
            "• 🚫 <b>TUYỆT ĐỐI KHÔNG FREESHIP & KHÔNG SPAM</b>\n\n"
            "Chọn chức năng bên dưới để bắt đầu:"
        )

    async def handle_super_vouchers(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý nút: 🔥 Mã siêu xịn (Chia 2 nhóm 90-100 và 80-89)"""
        vouchers = self.voucher_repo.get_all_vouchers()
        super_list = []
        worthy_list = []

        for v in vouchers:
            score, label, _ = calculate_elite_score(v)
            if score >= 90:
                super_list.append((v, score))
            elif score >= 80:
                worthy_list.append((v, score))

        # Sắp xếp điểm cao lên trước
        super_list.sort(key=lambda x: x[1], reverse=True)
        worthy_list.sort(key=lambda x: x[1], reverse=True)

        lines = ["💎 <b>DANH SÁCH VOUCHER ELITE (>= 80 ĐIỂM)</b>\n"]

        if super_list:
            lines.append("🔥 <b>SIÊU XỊN (90–100 điểm):</b>")
            for v, sc in super_list[:5]:
                code = v.voucher_code or "CHƯA CÔNG BỐ"
                lines.append(f"• <code>{code}</code>: Giảm {format_discount_display(v)} (Đơn {format_currency(v.min_order_value)}) [{sc}đ]")
            lines.append("")

        if worthy_list:
            lines.append("✅ <b>ĐÁNG LẤY (80–89 điểm):</b>")
            for v, sc in worthy_list[:5]:
                code = v.voucher_code or "CHƯA CÔNG BỐ"
                lines.append(f"• <code>{code}</code>: Giảm {format_discount_display(v)} (Đơn {format_currency(v.min_order_value)}) [{sc}đ]")
            lines.append("")

        if not super_list and not worthy_list:
            lines.append("<i>Hiện tại chưa có mã nào đạt chuẩn Elite (>= 80 điểm). Hãy bấm 'Quét ngay' để cập nhật!</i>")

        return "\n".join(lines), get_elite_back_keyboard()

    async def handle_upcoming_vouchers(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý nút: 📅 Sắp mở (Trong 7 ngày, xếp theo giờ gần nhất -> điểm -> giá trị)"""
        upcoming_raw = self.voucher_repo.get_upcoming_vouchers(days=self.settings["lookahead_days"])
        elite_upcoming = []

        for v in upcoming_raw:
            score, label, _ = calculate_elite_score(v)
            if score >= self.settings["min_elite_score"]:
                dt = parse_vietnam_dt(v.start_time)
                ts = dt.timestamp() if dt else 9999999999
                elite_upcoming.append((v, score, ts, v.discount_value))

        # Thứ tự: 1. Giờ gần nhất, 2. Điểm cao hơn, 3. Giảm lớn hơn
        elite_upcoming.sort(key=lambda x: (x[2], -x[1], -x[3]))

        lines = [f"📅 <b>MÃ ELITE SẮP MỞ ({self.settings['lookahead_days']} NGÀY TỚI)</b>\n"]
        if not elite_upcoming:
            lines.append("<i>Chưa có mã sắp mở nào đạt chuẩn Elite >= 80 điểm.</i>")
        else:
            for v, sc, _, _ in elite_upcoming[:8]:
                code = v.voucher_code or "SỰ KIỆN (CHƯA CODE)"
                lines.append(f"• <code>{code}</code>: Giảm {format_discount_display(v)} (Đơn {format_currency(v.min_order_value)}) [{sc}đ]\n  ⏰ <i>Mở: {v.start_time}</i>")

        return "\n".join(lines), get_elite_back_keyboard()

    async def handle_shop_vouchers(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý nút: 🏪 Mã shop (Chỉ hiện voucher Elite của shop được theo dõi)"""
        tracked = self.shop_repo.get_tracked_shops(enabled_only=True)
        tracked_ids = {str(s.shop_id).lower() for s in tracked} | {str(s.shop_name).lower() for s in tracked if s.shop_name}

        all_v = self.voucher_repo.get_all_vouchers()
        shop_vouchers = []

        for v in all_v:
            if v.scope_type == ScopeType.SHOP or v.shop_id:
                s_id = str(v.shop_id or "").lower()
                s_name = str(v.shop_name or "").lower()
                if (s_id in tracked_ids) or (s_name in tracked_ids):
                    score, _, _ = calculate_elite_score(v, is_tracked_shop=True)
                    if score >= self.settings["min_elite_score"]:
                        shop_vouchers.append((v, score))

        shop_vouchers.sort(key=lambda x: x[1], reverse=True)

        lines = ["🏪 <b>MÃ SHOP ĐƯỢC THEO DÕI (CHUẨN ELITE)</b>\n"]
        if not tracked:
            lines.append("<i>Bạn chưa theo dõi shop nào. Hãy gửi link shop để thêm vào radar!</i>")
        elif not shop_vouchers:
            lines.append("<i>Các shop bạn theo dõi hiện chưa có mã nào đạt chuẩn Elite (>= 80đ).</i>")
        else:
            for v, sc in shop_vouchers[:8]:
                code = v.voucher_code or "CHƯA LỘ"
                sname = v.shop_name or "Shop"
                lines.append(f"• <b>{sname}</b>: <code>{code}</code> Giảm {format_discount_display(v)} (Đơn {format_currency(v.min_order_value)}) [{sc}đ]")

        return "\n".join(lines), get_elite_back_keyboard()

    async def handle_scan_now(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý nút: 🔍 Quét ngay (Trả về báo cáo tổng kết chuẩn Section 9)"""
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
        """Xử lý nút: ⚙️ Cài đặt (Không có tùy chọn freeship)"""
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

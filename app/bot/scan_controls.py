import re
import urllib.parse
from typing import Dict, Any, Tuple, Optional
from repositories.voucher_repository import VoucherRepository
from repositories.shop_repository import ShopRepository
from services.discovery_service import DiscoveryService
from models.voucher import ScopeType, VoucherStatus
from models.scan_run import ScanMode
from app.bot.notification_templates import (
    format_scan_summary,
    format_currency,
    format_discount_value
)
from app.bot.keyboard_factory import get_main_keyboard, get_back_keyboard

class ScanControls:
    def __init__(
        self,
        voucher_repo: Optional[VoucherRepository] = None,
        shop_repo: Optional[ShopRepository] = None,
        discovery_service: Optional[DiscoveryService] = None
    ):
        self.voucher_repo = voucher_repo or VoucherRepository()
        self.shop_repo = shop_repo or ShopRepository()
        self.discovery_service = discovery_service or DiscoveryService(self.voucher_repo)

    async def execute_manual_scan(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý nút '🔍 Quét ngay' (MANUAL_ALL)"""
        scan_res = await self.discovery_service.run_scan(ScanMode.MANUAL_ALL)
        upcoming = self.voucher_repo.get_upcoming_vouchers(days=7)
        msg = format_scan_summary(scan_res, upcoming_count=len(upcoming))
        return msg, get_main_keyboard()

    def get_platform_view(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý nút '🌐 Mã toàn sàn'"""
        active_list = self.voucher_repo.get_vouchers(status=VoucherStatus.ACTIVE)
        platform_active = [v for v in active_list if v.scope_type in (ScopeType.PLATFORM, ScopeType.CATEGORY)]
        
        upcoming_list = self.voucher_repo.get_upcoming_vouchers(days=7)
        platform_upcoming = [v for v in upcoming_list if v.scope_type in (ScopeType.PLATFORM, ScopeType.CATEGORY)]

        lines = ["🌐 <b>KHO MÃ TOÀN SÀN & NGÀNH HÀNG SHOPEE</b>\n"]

        lines.append("🟢 <b>ĐANG HOẠT ĐỘNG:</b>")
        if not platform_active:
            lines.append("• <i>Hiện chưa có mã toàn sàn active.</i>")
        else:
            for v in platform_active[:5]:
                code_text = f"<code>{v.voucher_code}</code>" if v.voucher_code else "Lưu banner"
                lines.append(f"• {code_text} — Giảm {format_discount_value(v)} (Đơn {format_currency(v.min_order_value)})")

        lines.append("\n📅 <b>SẮP MỞ:</b>")
        if not platform_upcoming:
            lines.append("• <i>Chưa phát hiện sự kiện sắp mở trong 7 ngày tới.</i>")
        else:
            for v in platform_upcoming[:5]:
                code_text = f"<code>{v.voucher_code}</code>" if v.voucher_code else "Chưa công bố code"
                lines.append(f"• {code_text} — Mở: {v.start_time} (Giảm {format_discount_value(v)})")

        return "\n".join(lines), get_back_keyboard()

    def get_shops_view(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý nút '🏪 Mã từ shop'"""
        shops = self.shop_repo.get_tracked_shops(enabled_only=True)
        if not shops:
            msg = (
                "🏪 <b>CHƯA CÓ SHOP NÀO ĐƯỢC THEO DÕI</b>\n\n"
                "Bạn chưa thêm gian hàng nào vào danh sách.\n"
                "👉 Hãy bấm nút <b>➕ Thêm shop</b> hoặc gửi link shop để bắt đầu theo dõi voucher riêng của shop!"
            )
            return msg, get_back_keyboard()

        shop_vouchers = self.voucher_repo.get_vouchers(scope_type=ScopeType.SHOP)

        lines = [f"🏪 <b>MÃ TỪ CÁC SHOP ĐANG THEO DÕI ({len(shops)} shop):</b>\n"]
        for s in shops[:6]:
            v_of_shop = [v for v in shop_vouchers if v.shop_id == s.shop_id]
            lines.append(f"🏬 <b>{s.shop_name}</b>")
            if v_of_shop:
                for v in v_of_shop[:2]:
                    code_text = f"<code>{v.voucher_code}</code>" if v.voucher_code else "Voucher shop"
                    lines.append(f"  └ {code_text}: Giảm {format_discount_value(v)} (Đơn {format_currency(v.min_order_value)})")
            else:
                lines.append("  └ <i>Chưa có voucher giảm giá hàng.</i>")

        return "\n".join(lines), get_back_keyboard()

    def get_upcoming_view(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý nút '📅 Mã sắp mở' (7 ngày tới)"""
        upcoming = self.voucher_repo.get_upcoming_vouchers(days=7)
        if not upcoming:
            return "📅 <b>Chưa có mã hoặc sự kiện nào sắp mở trong 7 ngày tới.</b>\n<i>Hệ thống sẽ tự động quét và báo ngay khi có đợt mã mới.</i>", get_back_keyboard()

        lines = ["📅 <b>DANH SÁCH MÃ & SỰ KIỆN SẮP MỞ (7 NGÀY TỚI)</b>\n"]
        for v in upcoming[:8]:
            code_text = f"<code>{v.voucher_code}</code>" if v.voucher_code else "<i>(Chưa lộ mã)</i>"
            scope_badge = "Toàn sàn" if v.scope_type == ScopeType.PLATFORM else ("Shop" if v.scope_type == ScopeType.SHOP else "Ngành")
            lines.append(
                f"⏰ <b>{v.start_time}</b> [{scope_badge}]\n"
                f"• Mã: {code_text}\n"
                f"• Giảm: {format_discount_value(v)} (Đơn tối thiểu {format_currency(v.min_order_value)})\n"
                f"• Nguồn: <a href=\"{v.source_url}\">Xem trang sự kiện</a>\n"
            )

        return "\n".join(lines), get_back_keyboard()

    def parse_and_add_shop(self, raw_input: str) -> Tuple[str, bool]:
        """Phân tích link shop công khai và thêm vào tracked_shops"""
        clean_input = raw_input.strip()
        # Tìm URL trong văn bản
        m_url = re.search(r'https?://[^\s]+', clean_input)
        url = m_url.group(0) if m_url else clean_input

        if not url.startswith("http"):
            url = f"https://shopee.vn/{clean_input}"

        parsed = urllib.parse.urlparse(url)
        path = parsed.path.strip("/")
        parts = [p for p in path.split("/") if p]

        if not parts:
            return "❌ Link shop không hợp lệ. Vui lòng gửi link dạng https://shopee.vn/ten_shop", False

        shop_identifier = parts[0]
        # Bỏ qua các đường dẫn hệ thống
        if shop_identifier in ("m", "universal-link", "cart", "user", "buyer"):
            if len(parts) > 1:
                shop_identifier = parts[1]
            else:
                return "❌ Không nhận diện được tên shop từ đường link này.", False

        shop_name = shop_identifier.replace("-", " ").title()
        shop_url = f"https://shopee.vn/{shop_identifier}"

        self.shop_repo.add_shop(shop_id=shop_identifier, shop_name=shop_name, shop_url=shop_url)
        msg = (
            f"✅ <b>ĐÃ THÊM SHOP VÀO THEO DÕI THÀNH CÔNG!</b>\n\n"
            f"• Tên shop: <b>{shop_name}</b>\n"
            f"• Mã shop: <code>{shop_identifier}</code>\n"
            f"• Đường dẫn: <a href=\"{shop_url}\">{shop_url}</a>\n\n"
            "Bot sẽ tự động quét và báo ngay khi shop này tung mã giảm giá mới!"
        )
        return msg, True

    def remove_shop(self, identifier: str) -> str:
        """Xóa shop khỏi danh sách theo dõi"""
        deleted = self.shop_repo.remove_shop(identifier.strip())
        if deleted:
            return f"✅ Đã xóa shop <code>{identifier}</code> khỏi danh sách theo dõi."
        return f"❌ Không tìm thấy shop <code>{identifier}</code> trong danh sách theo dõi."

    def get_settings_view(self) -> Tuple[str, Dict[str, Any]]:
        """Xử lý nút '⚙️ Cài đặt'"""
        msg = (
            "⚙️ <b>CÀI ĐẶT RADAR SHOPEE</b>\n"
            "────────────────────\n"
            "• Sàn theo dõi: <b>Shopee Vietnam</b> (Duy nhất)\n"
            "• Ngưỡng báo mã cố định: <b>Từ 50.000đ</b>\n"
            "• Ngưỡng báo mã %: <b>Từ 15% (tối đa từ 100.000đ)</b>\n"
            "• Thời gian xem trước: <b>7 ngày</b>\n"
            "• Lời nhắc giờ mở: <b>15 phút & 2 phút trước giờ mở</b>\n"
            "• Chính sách Freeship: <b>Loại bỏ tuyệt đối 100% (Zero Freeship)</b>\n\n"
            "💡 <i>Mọi cài đặt đang hoạt động tối ưu theo chuẩn cá nhân của bạn.</i>"
        )
        return msg, get_back_keyboard()

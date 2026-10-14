from typing import Dict, Any, Optional

def get_elite_main_keyboard() -> Dict[str, Any]:
    """Bàn phím chính tối giản 3 nút cốt lõi:
    [ 🔥 Mã Đơn 0Đ Đang Mở ]   [ ⏳ Lịch Săn Khung Giờ ]
    [ 🔍 Quét Ngay ]
    """
    return {
        "inline_keyboard": [
            [
                {"text": "🔥 Mã Đơn 0Đ Đang Mở", "callback_data": "action:zero_dong_active"},
                {"text": "⏳ Lịch Săn Khung Giờ", "callback_data": "action:zero_dong_upcoming"}
            ],
            [
                {"text": "🔍 Quét Ngay", "callback_data": "action:zero_dong_scan"}
            ]
        ]
    }

def get_elite_voucher_action_keyboard(
    source_url: str = "https://shopee.vn",
    shop_url: Optional[str] = None,
    voucher_id: Optional[str] = None,
    claim_type: str = "CODE"
) -> Optional[Dict[str, Any]]:
    """Giao diện hành động voucher tối giản:
    - Nếu là mã lưu banner: Hiển thị duy nhất 1 nút [ 🚀 Mở App Lưu Mã ]
    - Nếu là mã nhập tay: Người dùng copy 1-chạm tại code block
    """
    target_link = shop_url or source_url or "https://shopee.vn"
    if claim_type in ("BANNER", "COMMUNITY_LEAK", "SAVE_BUTTON"):
        return {
            "inline_keyboard": [
                [
                    {"text": "🚀 Mở App Lưu Mã", "url": target_link}
                ]
            ]
        }
    return None

def get_elite_back_keyboard() -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "🔙 Menu chính", "callback_data": "action:elite_menu"}]
        ]
    }


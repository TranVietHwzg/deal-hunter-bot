from typing import Dict, Any, List

def get_main_keyboard() -> Dict[str, Any]:
    """Bàn phím Inline Keyboard 6 nút chuẩn tối giản"""
    return {
        "inline_keyboard": [
            [
                {"text": "🔍 Quét ngay", "callback_data": "action:scan_now"},
                {"text": "🌐 Mã toàn sàn", "callback_data": "action:platform"}
            ],
            [
                {"text": "🏪 Mã từ shop", "callback_data": "action:shops"},
                {"text": "📅 Mã sắp mở", "callback_data": "action:upcoming"}
            ],
            [
                {"text": "➕ Thêm shop", "callback_data": "action:add_shop"},
                {"text": "⚙️ Cài đặt", "callback_data": "action:settings"}
            ]
        ]
    }

def get_voucher_action_keyboard(source_url: str = "https://shopee.vn") -> Dict[str, Any]:
    """Bàn phím hành động cho thẻ voucher: Quét lại & Mở nguồn"""
    return {
        "inline_keyboard": [
            [
                {"text": "🔄 Quét lại", "callback_data": "action:scan_now"},
                {"text": "🌐 Mở nguồn", "url": source_url or "https://shopee.vn"}
            ]
        ]
    }

def get_back_keyboard() -> Dict[str, Any]:
    """Nút quay lại menu chính"""
    return {
        "inline_keyboard": [
            [
                {"text": "🔙 Menu chính", "callback_data": "action:menu"}
            ]
        ]
    }

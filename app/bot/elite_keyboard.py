from typing import Dict, Any, Optional

def get_elite_main_keyboard() -> Dict[str, Any]:
    """Bàn phím chính 5 nút chuẩn Elite Shopee Voucher Radar:
    🔥 Mã siêu xịn
    📅 Sắp mở      🏪 Mã shop
    🔍 Quét ngay   ⚙️ Cài đặt
    """
    return {
        "inline_keyboard": [
            [
                {"text": "🔥 Mã siêu xịn", "callback_data": "action:elite_super"}
            ],
            [
                {"text": "📅 Sắp mở", "callback_data": "action:elite_upcoming"},
                {"text": "🏪 Mã shop", "callback_data": "action:elite_shops"}
            ],
            [
                {"text": "🔍 Quét ngay", "callback_data": "action:elite_scan_now"},
                {"text": "⚙️ Cài đặt", "callback_data": "action:elite_settings"}
            ]
        ]
    }

def get_elite_voucher_action_keyboard(
    source_url: str = "https://shopee.vn",
    shop_url: Optional[str] = None,
    voucher_id: Optional[str] = None,
    claim_type: str = "CODE"
) -> Dict[str, Any]:
    """Bàn phím tương tác voucher luôn có 2 link: 🏪 Mở shop / Lưu + 🌐 Mở nguồn
    Kèm hàng nút Crowdsourced Feedback: 👍 Còn dùng được + ❌ Báo hết lượt
    """
    target_shop = shop_url or source_url or "https://shopee.vn"
    target_source = source_url or "https://shopee.vn"
    
    first_btn_text = "📥 Bấm lưu trên Shopee" if claim_type in ("BANNER", "COMMUNITY_LEAK") else "🏪 Mở shop / Lưu"
    
    buttons = [
        [
            {"text": first_btn_text, "url": target_shop},
            {"text": "🌐 Mở nguồn", "url": target_source}
        ]
    ]
    if voucher_id:
        buttons.append([
            {"text": "👍 Còn dùng được", "callback_data": f"fb:like:{voucher_id}"},
            {"text": "❌ Báo hết lượt", "callback_data": f"fb:exhaust:{voucher_id}"}
        ])
    return {"inline_keyboard": buttons}

def get_elite_back_keyboard() -> Dict[str, Any]:
    return {
        "inline_keyboard": [
            [{"text": "🔙 Menu chính", "callback_data": "action:elite_menu"}]
        ]
    }

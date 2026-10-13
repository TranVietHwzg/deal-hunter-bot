import re
import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

from sources.base_source import BaseVoucherSource
from core.voucher_filter import is_freeship, is_worthy_voucher
from models.voucher import VerificationStatus

VN_TZ = timezone(timedelta(hours=7))

class TelegramChannelSource(BaseVoucherSource):
    """
    Nguồn lắng nghe các Kênh Telegram Săn Deal công khai (Telegram Public Channel Preview).
    - Quét web preview tĩnh không cần tài khoản / API key / token (https://t.me/s/<channel>).
    - Trích xuất mã nhập tay (code) và link bấm lưu trực tiếp từ các kênh deal lớn trước giờ G.
    - Gán nhãn COMMUNITY_LEAK (Mã leak cộng đồng) cho các mã đạt chuẩn >= 30k đơn 0đ hoặc >= 30%.
    """
    def __init__(self, channels: Optional[List[str]] = None):
        super().__init__(
            name="telegram_channel_source",
            source_type="TELEGRAM_COMMUNITY",
            rate_limit_per_minute=20,
            failure_threshold=4
        )
        self.channels = channels or [
            "magiamgiashopee",
            "nghienshopee",
            "dealshopee",
            "hoisandeal"
        ]
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7"
        }

    def _parse_message(self, raw_html: str, channel_name: str) -> Optional[Dict[str, Any]]:
        # 1. Trích xuất code nhập tay
        code_match = re.search(r'<code>([A-Za-z0-9_-]{4,25})</code>', raw_html)
        if not code_match:
            code_match = re.search(r'(?:nhập|lưu|mã|code)\s*:?\s*<b>([A-Za-z0-9_-]{4,25})</b>', raw_html, re.IGNORECASE)
        if not code_match:
            code_match = re.search(r'(?:nhập mã|lưu mã|mã code|nhập|code)\s*:?\s*([A-Za-z0-9]{4,25})\b', raw_html, re.IGNORECASE)

        code = code_match.group(1).upper() if code_match else None
        # Loại trừ một số từ ngữ nhầm lẫn thành code
        if code in ("SHOPEE", "VOUCHER", "FREE", "FREESHIP", "MALL", "LIVE", "VIDEO", "HTTP", "HTTPS"):
            code = None

        clean_text = re.sub(r'<[^>]+>', ' ', raw_html)
        clean_text = ' '.join(clean_text.split())

        # 2. Mức giảm (discount value & type)
        pct_m = re.search(r'(\d{1,2})\s*%', clean_text)
        fixed_m = re.search(r'(?:giảm|voucher|mã|back)\s*(\d{1,4})\s*[kK]', clean_text, re.IGNORECASE)

        is_pct = False
        dval = 0.0
        max_d = None

        if pct_m and int(pct_m.group(1)) >= 10:
            is_pct = True
            dval = float(pct_m.group(1))
            cap_m = re.search(r'(?:tối đa|max|trần|cap)\s*(\d{1,4})\s*[kK]', clean_text, re.IGNORECASE)
            if cap_m:
                max_d = float(cap_m.group(1)) * 1000
            elif dval >= 30:
                max_d = 50000.0
        elif fixed_m:
            dval = float(fixed_m.group(1)) * 1000

        # Nếu không bắt được discount từ regex cụ thể nhưng có ghi mã 80k/0đ hoặc 50k/0đ
        if dval == 0:
            ratio_m = re.search(r'(\d{1,3})[kK]/0[đkK]?', clean_text)
            if ratio_m:
                dval = float(ratio_m.group(1)) * 1000

        # 3. Đơn tối thiểu
        min_o = 0.0
        min_m = re.search(r'đơn\s*(?:từ\s*)?(\d{1,4})\s*[kK]', clean_text, re.IGNORECASE)
        if min_m:
            min_o = float(min_m.group(1)) * 1000
        elif re.search(r'đơn\s*(?:từ\s*)?0[đkK]?', clean_text, re.IGNORECASE) or re.search(r'\/0[đkK]', clean_text):
            min_o = 0.0

        # 4. Link Shopee thực tế
        shopee_link_m = re.search(r'href=[\'"](https://[^\'"]*shopee[^\'"]*)[\'"]', raw_html)
        source_url = shopee_link_m.group(1) if shopee_link_m else f"https://t.me/s/{channel_name}"

        # 5. Thời gian hiệu lực
        now = datetime.now(VN_TZ)
        today_str = now.strftime("%d/%m/%Y")
        hour_m = re.search(r'\b(\d{1,2})[hH](?:(\d{2}))?\b', clean_text)
        start_time = f"00:00 {today_str}"
        if hour_m:
            h = int(hour_m.group(1))
            if 0 <= h <= 23:
                mn = int(hour_m.group(2)) if hour_m.group(2) else 0
                start_time = f"{h:02d}:{mn:02d} {today_str}"
        end_time = f"23:59 {today_str}"

        # 6. Xác định claim_type và scope
        claim_type = "CODE" if code else "SAVE_BUTTON"
        scope_type = "PLATFORM"
        if "shop" in clean_text.lower():
            scope_type = "SHOP"
        elif "điện tử" in clean_text.lower() or "bách hóa" in clean_text.lower():
            scope_type = "CATEGORY"

        # Unique ID
        uid_key = code or (re.search(r'/([^/?]+)(?:\?|$)', source_url).group(1) if '/s/' in source_url or 'shopee' in source_url else f"{int(dval)}_{int(min_o)}")
        v_id = f"TG_{channel_name.upper()}_{uid_key}_{int(dval)}"

        title = f"Mã {code or 'săn deal'}: Giảm {int(dval)}{'%' if is_pct else 'đ'}"
        if "toàn sàn" in clean_text.lower():
            title += " toàn sàn"

        item = {
            "id": v_id,
            "voucher_code": code,
            "claim_type": claim_type,
            "verification_status": VerificationStatus.COMMUNITY_LEAK.value,
            "title": title,
            "description": clean_text[:200],
            "scope_type": scope_type,
            "discount_type": "PERCENT" if is_pct else "FIXED",
            "discount_value": dval,
            "max_discount": max_d,
            "min_order_value": min_o,
            "start_time": start_time,
            "end_time": end_time,
            "source_url": source_url,
            "source_type": "TELEGRAM_COMMUNITY",
            "source_title": f"Telegram @{channel_name}",
            "source_captured_at": now.isoformat(),
            "source_evidence_excerpt": clean_text[:250],
            "confidence_score": 85 if code else 75,
            "is_freeship": 0
        }

        # Lọc Zero Freeship & Worthy Voucher (>=30k đơn 0đ hoặc >=30%)
        is_ship, _ = is_freeship(item)
        if is_ship:
            return None

        if not is_worthy_voucher(item):
            return None

        return item

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        """Quét và trích xuất voucher từ các kênh Telegram săn deal công khai"""
        if not self.circuit_breaker.can_execute():
            return []

        await self.rate_limiter.acquire()
        vouchers = []
        seen_keys = set()

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                for ch in self.channels:
                    url = f"https://t.me/s/{ch}"
                    try:
                        resp = await client.get(url, headers=self.headers)
                        if resp.status_code == 200:
                            msgs = re.findall(
                                r'<div class="tgme_widget_message_text[^\"]*"\s+dir="auto">(.*?)</div>',
                                resp.text,
                                re.DOTALL
                            )
                            # Duyệt các tin nhắn mới nhất ở cuối trang
                            for raw_msg in reversed(msgs[-15:]):
                                item = self._parse_message(raw_msg, ch)
                                if item:
                                    key = item.get("voucher_code") or item.get("source_url") or item.get("id")
                                    if key and key not in seen_keys:
                                        seen_keys.add(key)
                                        vouchers.append(item)
                    except Exception:
                        pass

            self.circuit_breaker.record_success()
        except Exception:
            self.circuit_breaker.record_failure()

        return vouchers

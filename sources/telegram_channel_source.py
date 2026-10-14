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

    def _parse_message(self, raw_html: str, channel_name: str, post_dt: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
        # 0. Xác định thời gian đăng bài
        now = datetime.now(VN_TZ)
        if post_dt is None:
            time_m = re.search(r'<time[^>]*datetime=[\'"]([^\'"]+)[\'"]', raw_html)
            if time_m:
                try:
                    clean_iso = time_m.group(1).replace("Z", "+00:00")
                    post_dt = datetime.fromisoformat(clean_iso).astimezone(VN_TZ)
                except Exception:
                    pass
        if post_dt is None:
            post_dt = now

        # Bỏ qua ngay các bài viết cũ hơn 48h
        if post_dt < now - timedelta(hours=48):
            return None

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

        # 5. Thời gian hiệu lực chuẩn xác: Gắn vào ngày của bài viết (post_dt), tuyệt đối không gán now.
        # Hỗ trợ ngày tháng nằm trong ngoặc đơn phía sau khung giờ, ví dụ: "12h (14/10)" hoặc "20:00 (29/09/2026)".
        base_year = post_dt.year
        base_month = post_dt.month
        base_day = post_dt.day
        paren_date_m = re.search(r'\(\s*(\d{1,2})/(\d{1,2})(?:/(\d{4}))?\s*\)', clean_text)
        has_explicit_date = bool(paren_date_m)
        if paren_date_m:
            cand_day = int(paren_date_m.group(1))
            cand_month = int(paren_date_m.group(2))
            cand_year_provided = bool(paren_date_m.group(3))
            cand_year = int(paren_date_m.group(3)) if cand_year_provided else base_year
            try:
                cand_dt = datetime(cand_year, cand_month, cand_day, tzinfo=VN_TZ)
                if (not cand_year_provided and (now - cand_dt).days > 60
                        and cand_month <= 2 and now.month >= 10):
                    cand_year += 1
                    cand_dt = datetime(cand_year, cand_month, cand_day, tzinfo=VN_TZ)
                base_year = cand_year
                base_month = cand_month
                base_day = cand_day
            except ValueError:
                pass

        hour_m = re.search(r'\b(0|9|12|15|18|20|21|24)\s*[hH](?:(\d{2}))?\b', clean_text)
        if hour_m:
            slot_h = int(hour_m.group(1))
            if slot_h == 24:
                slot_h = 0
            slot_m = int(hour_m.group(2)) if hour_m.group(2) else 0
            start_dt = datetime(base_year, base_month, base_day, slot_h, slot_m, second=0, microsecond=0, tzinfo=VN_TZ)
            end_dt = start_dt + timedelta(minutes=30)
        else:
            # Nếu bài đăng không ghi rõ khung giờ (ví dụ "mã 50k sẵn ví"):
            start_dt = post_dt.replace(year=base_year, month=base_month, day=base_day) if has_explicit_date else post_dt
            end_dt = start_dt + timedelta(minutes=45)

        # Expiry-Guard: nếu bài viết chỉ rõ ngày tháng trong ngoặc và đã qua hạn -> bỏ qua để chống spam mã cũ
        if has_explicit_date and end_dt < now:
            return None
        start_time = start_dt.strftime("%Y-%m-%d %H:%M:%S")
        end_time = end_dt.strftime("%Y-%m-%d %H:%M:%S")

        # 6. Xác định claim_type và scope
        claim_type = "CODE" if code else "SAVE_BUTTON"
        scope_type = "PLATFORM"
        if "shop" in clean_text.lower():
            scope_type = "SHOP"
        elif "điện tử" in clean_text.lower() or "bách hóa" in clean_text.lower():
            scope_type = "CATEGORY"

        # Unique ID gắn với ngày đăng
        uid_key = code or (re.search(r'/([^/?]+)(?:\?|$)', source_url).group(1) if '/s/' in source_url or 'shopee' in source_url else f"{int(dval)}_{int(min_o)}")
        v_id = f"TG_{channel_name.upper()}_{uid_key}_{int(dval)}_{post_dt.strftime('%Y%m%d')}"

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
            "claim_url": source_url,
            "source_url": source_url,
            "source_type": "TELEGRAM_COMMUNITY",
            "source_title": f"Telegram @{channel_name}",
            "source_captured_at": post_dt.isoformat(),
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
        now = datetime.now(VN_TZ)

        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                for ch in self.channels:
                    url = f"https://t.me/s/{ch}"
                    try:
                        resp = await client.get(url, headers=self.headers)
                        if resp.status_code == 200:
                            blocks = re.split(r'<div class="tgme_widget_message\b', resp.text)
                            for block in reversed(blocks[1:]):
                                text_m = re.search(r'<div class="tgme_widget_message_text[^\"]*"\s+dir="auto">(.*?)</div>', block, re.DOTALL)
                                if not text_m:
                                    continue
                                time_m = re.search(r'<time[^>]*datetime=[\'"]([^\'"]+)[\'"]', block)
                                msg_dt = None
                                if time_m:
                                    try:
                                        clean_iso = time_m.group(1).replace("Z", "+00:00")
                                        msg_dt = datetime.fromisoformat(clean_iso).astimezone(VN_TZ)
                                    except Exception:
                                        pass

                                # Bỏ qua bài viết cũ hơn 48h
                                if msg_dt and msg_dt < now - timedelta(hours=48):
                                    continue

                                item = self._parse_message(block, ch, post_dt=msg_dt)
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

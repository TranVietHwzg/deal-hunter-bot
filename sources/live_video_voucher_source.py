"""Nguồn thu thập voucher Shopee Live / Video (Read-only observation).
Quét các trang sự kiện công khai của Shopee Live / Video / Khung Giờ Vàng.
Khi phát hiện mã khung giờ sắp mở (VD 20H) chưa lộ mã, phân loại là UPCOMING_UNKNOWN_CODE.
Tuyệt đối KHÔNG giả lập claim, không tạo mock/fixture giả.
"""
import re
import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sources.base_source import BaseVoucherSource
from core.voucher_filter import is_freeship, is_worthy_voucher

VN_TZ = timezone(timedelta(hours=7))

LIVE_CAMPAIGN_URLS = [
    "https://shopee.vn/m/khung-gio-vang",
    "https://shopee.vn/m/shopee-live",
    "https://shopee.vn/m/shopee-video",
]

GOLD_HOURS = [0, 9, 12, 18, 20, 21]

LIVE_DISCOUNT_FIXED_RE = re.compile(
    r"(?:Shopee\s*(?:Live|Video)|Khung\s*(\d{1,2})H)[^\n<]{0,100}?(?:giảm|voucher|deal)\s*(\d{1,3})(?:k|\.000|000)",
    re.IGNORECASE,
)
LIVE_DISCOUNT_PCT_RE = re.compile(
    r"(?:Shopee\s*(?:Live|Video)|Khung\s*(\d{1,2})H)[^\n<]{0,100}?(?:giảm|voucher)\s*(\d{1,2})\s*%",
    re.IGNORECASE,
)
CODE_RE = re.compile(
    r"(?:nhập mã|mã|code)[\s:]*([A-Z0-9]{4,25})",
    re.IGNORECASE,
)

class LiveVideoVoucherSource(BaseVoucherSource):
    """
    Nguồn thu thập voucher Shopee Live / Video từ các trang chiến dịch công khai.
    Hỗ trợ phát hiện voucher theo khung giờ (0H, 12H, 20H) và tự động gắn UPCOMING_UNKNOWN_CODE.
    """
    def __init__(self, urls: List[str] | None = None):
        super().__init__(
            name="live_video_voucher_source",
            source_type="LIVE_VIDEO",
            rate_limit_per_minute=20,
            failure_threshold=4,
        )
        self.urls = urls or LIVE_CAMPAIGN_URLS
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.7",
            "Referer": "https://shopee.vn/",
        }

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        if not self.circuit_breaker.can_execute():
            return []

        out: List[Dict[str, Any]] = []
        now = datetime.now(VN_TZ)
        today = now.strftime("%d/%m/%Y")
        seen_keys = set()

        try:
            async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                for url in self.urls:
                    await self.rate_limiter.acquire()
                    try:
                        resp = await client.get(url, headers=self.headers)
                    except Exception:
                        continue
                    if resp.status_code != 200:
                        continue

                    text = resp.text[:250000]

                    # 1. Quét voucher tiền cố định cho Live / Video / Khung giờ
                    for match in LIVE_DISCOUNT_FIXED_RE.finditer(text):
                        hour_str, amount_str = match.groups()
                        val = float(amount_str) * 1000
                        if val < 30000.0:
                            continue

                        slot_hour = int(hour_str) if hour_str else 20
                        start_pos = max(0, match.start() - 100)
                        end_pos = min(len(text), match.end() + 100)
                        context = text[start_pos:end_pos].lower()

                        min_match = re.search(r'đơn\s*(?:từ)?\s*(\d{1,3})(?:k|\.000|000)', context)
                        min_val = float(min_match.group(1)) * 1000 if min_match else 0.0

                        code_m = CODE_RE.search(text[start_pos:end_pos])
                        code = code_m.group(1).upper() if code_m else None
                        if code in ("SHOPEE", "LIVE", "VIDEO", "VOUCHER", "DISCOUNT"):
                            code = None

                        key = f"LIVE_{slot_hour}H_{int(val)}_{int(min_val)}_{code or 'UPCOMING'}"
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)

                        start_time_str = f"{slot_hour:02d}:00 {today}"
                        is_upcoming = not code or (slot_hour > now.hour)

                        item = {
                            "id": f"{key}_{today.replace('/', '')}",
                            "voucher_code": code,
                            "scope_type": "LIVE_VIDEO",
                            "title": f"Mã Shopee Live/Video {slot_hour}H: Giảm {int(val):,}đ" if not code else f"Mã Live {code}: Giảm {int(val):,}đ",
                            "description": f"Chỉ áp dụng trên Shopee Live/Video khung {slot_hour}H. Nguồn: {url}",
                            "discount_type": "FIXED",
                            "discount_value": val,
                            "max_discount": val,
                            "min_order_value": min_val,
                            "start_time": start_time_str,
                            "end_time": f"23:59 {today}",
                            "claim_url": url,
                            "source_url": url,
                            "source_type": "LIVE_VIDEO",
                            "confidence_score": 85 if code else 75,
                            "verification_status": "VERIFIED_ACTIVE" if (code and not is_upcoming) else ("UPCOMING_UNKNOWN_CODE" if not code else "VERIFIED_UPCOMING"),
                            "status": "UPCOMING_UNKNOWN_CODE" if not code else ("ACTIVE" if not is_upcoming else "UPCOMING_CODE_KNOWN"),
                            "is_freeship": 0,
                        }

                        if not is_freeship(item)[0] and is_worthy_voucher(item):
                            out.append(item)

                    # 2. Quét voucher % cho Live / Video / Khung giờ
                    for match in LIVE_DISCOUNT_PCT_RE.finditer(text):
                        hour_str, pct_str = match.groups()
                        pct = float(pct_str)
                        if pct < 30.0:
                            continue

                        slot_hour = int(hour_str) if hour_str else 20
                        start_pos = max(0, match.start() - 100)
                        end_pos = min(len(text), match.end() + 100)
                        context = text[start_pos:end_pos].lower()

                        cap_match = re.search(r'tối đa\s*(\d{1,3})(?:k|\.000|000)', context)
                        max_cap = float(cap_match.group(1)) * 1000 if cap_match else 30000.0

                        min_match = re.search(r'đơn\s*(?:từ)?\s*(\d{1,3})(?:k|\.000|000)', context)
                        min_val = float(min_match.group(1)) * 1000 if min_match else 0.0

                        code_m = CODE_RE.search(text[start_pos:end_pos])
                        code = code_m.group(1).upper() if code_m else None
                        if code in ("SHOPEE", "LIVE", "VIDEO", "VOUCHER", "DISCOUNT"):
                            code = None

                        key = f"LIVE_PCT_{slot_hour}H_{int(pct)}_{int(max_cap)}_{code or 'UPCOMING'}"
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)

                        start_time_str = f"{slot_hour:02d}:00 {today}"
                        is_upcoming = not code or (slot_hour > now.hour)

                        item = {
                            "id": f"{key}_{today.replace('/', '')}",
                            "voucher_code": code,
                            "scope_type": "LIVE_VIDEO",
                            "title": f"Mã Shopee Live/Video {slot_hour}H: Giảm {int(pct)}% tối đa {int(max_cap):,}đ" if not code else f"Mã Live {code}: Giảm {int(pct)}%",
                            "description": f"Chỉ áp dụng trên Shopee Live/Video khung {slot_hour}H. Nguồn: {url}",
                            "discount_type": "PERCENT",
                            "discount_value": pct,
                            "max_discount": max_cap,
                            "min_order_value": min_val,
                            "start_time": start_time_str,
                            "end_time": f"23:59 {today}",
                            "claim_url": url,
                            "source_url": url,
                            "source_type": "LIVE_VIDEO",
                            "confidence_score": 85 if code else 75,
                            "verification_status": "VERIFIED_ACTIVE" if (code and not is_upcoming) else ("UPCOMING_UNKNOWN_CODE" if not code else "VERIFIED_UPCOMING"),
                            "status": "UPCOMING_UNKNOWN_CODE" if not code else ("ACTIVE" if not is_upcoming else "UPCOMING_CODE_KNOWN"),
                            "is_freeship": 0,
                        }

                        if not is_freeship(item)[0] and is_worthy_voucher(item):
                            out.append(item)

        except Exception:
            self.circuit_breaker.record_failure()
            return out

        self.circuit_breaker.record_success()
        return out[:30]

"""Nguồn banner công khai mở rộng - chỉ đọc trang public, tôn trọng rate-limit.
Không vượt tường đăng nhập, không brute-force mã, không tự claim.
"""
import re
import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sources.base_source import BaseVoucherSource
from core.voucher_filter import is_freeship

VN_TZ = timezone(timedelta(hours=7))

# Chỉ các trang chiến dịch công khai của Shopee
PUBLIC_URLS = [
    "https://shopee.vn/m/ma-giam-gia",
    "https://shopee.vn/m/khung-gio-vang",
    "https://shopee.vn/m/sieu-sale-cong-nghe",
    "https://shopee.vn/mall",
]

# Tìm mã nhập tay lộ rõ trong text: VD "Nhập mã SIEUHOI100K"
CODE_HINT_RE = re.compile(
    r"(?:nhập mã|nhap ma|mã|code)[\s:]*([A-Z0-9]{4,25})",
    re.IGNORECASE,
)

class PublicBannerSource(BaseVoucherSource):
    def __init__(self, urls: List[str] | None = None):
        super().__init__(
            name="public_banner_source",
            source_type="PUBLIC_BANNER",
            rate_limit_per_minute=15,
            failure_threshold=4,
        )
        self.urls = urls or PUBLIC_URLS
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
                    text = resp.text[:200000]
                    # chỉ lấy code xuất hiện kèm từ khóa khuyến mãi, tránh rác
                    for m in set(CODE_HINT_RE.findall(text)):
                        code = m.strip().upper()
                        if len(code) < 4 or len(code) > 25:
                            continue
                        # Bỏ từ chung chung
                        if code in ("SALE", "VOUCHER", "SHOPEE", "MALL", "CODE", "PROMO", "DISCOUNT", "VOUCHERS"):
                            continue
                        
                        # Tìm số tiền hoặc % giảm trong vùng lân cận (100 ký tự xung quanh code)
                        pos = text.upper().find(code)
                        context = text[max(0, pos - 100):min(len(text), pos + 100)].lower() if pos != -1 else ""
                        
                        # Tìm giảm tiền: vd 50k, 100k, 50.000đ
                        val_match = re.search(r'giảm\s*(\d{1,3})(?:k|\.000|000)', context)
                        pct_match = re.search(r'giảm\s*(\d{1,2})\s*%', context)
                        min_match = re.search(r'đơn\s*(?:từ)?\s*(\d{1,3})(?:k|\.000|000)', context)
                        
                        if val_match:
                            d_val = float(val_match.group(1)) * 1000
                            d_type = "FIXED"
                        elif pct_match:
                            d_val = float(pct_match.group(1))
                            d_type = "PERCENT"
                        else:
                            # Không xác định được giá trị giảm thật -> Bỏ qua, tuyệt đối không bịa số tiền
                            continue

                        min_val = float(min_match.group(1)) * 1000 if min_match else 0
                        
                        item = {
                            "id": f"PB_{code}_{today.replace('/','')}",
                            "voucher_code": code,
                            "scope_type": "PLATFORM",
                            "title": f"Mã công khai từ banner: {code}",
                            "description": f"Phát hiện công khai tại {url}, nhập tay ở bước thanh toán.",
                            "discount_type": d_type,
                            "discount_value": d_val,
                            "max_discount": d_val if d_type == "FIXED" else d_val * 1000,
                            "min_order_value": min_val,
                            "start_time": f"00:00 {today}",
                            "end_time": f"23:59 {today}",
                            "claim_url": url,
                            "source_url": url,
                            "source_type": "PUBLIC_BANNER",
                            "confidence_score": 85,
                            "is_freeship": 0,
                        }
                        if not is_freeship(item)[0]:
                            out.append(item)
        except Exception:
            self.circuit_breaker.record_failure()
            return out
        self.circuit_breaker.record_success()
        # giới hạn chống spam
        return out[:30]

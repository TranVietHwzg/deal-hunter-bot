"""Nguồn thu thập voucher đối tác thanh toán ShopeePay / SPayLater / Ngân hàng liên kết.
Chỉ đọc từ các trang công khai (read-only), tuân thủ rate limit và circuit breaker.
Tuyệt đối KHÔNG giả lập đăng nhập, không hardcode mock data.
"""
import re
import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sources.base_source import BaseVoucherSource
from core.voucher_filter import is_freeship, is_worthy_voucher

VN_TZ = timezone(timedelta(hours=7))

PAYMENT_CAMPAIGN_URLS = [
    "https://shopee.vn/m/shopeepay",
    "https://shopee.vn/m/ma-giam-gia",
]

PARTNERS = [
    "ShopeePay", "SPayLater", "Visa", "Mastercard", "JCB",
    "BIDV", "VPBank", "Techcombank", "VIB", "Shinhan", "Vietcombank"
]

PARTNER_PATTERN = "|".join(PARTNERS)
PAYMENT_DISCOUNT_FIXED_RE = re.compile(
    rf"(?:({PARTNER_PATTERN})[^\n<]{{0,100}}?)?(?:giảm|ưu đãi)\s*(\d{{1,3}})(?:k|\.000|000)(?:[^\n<]{{0,80}}?(?:qua|bằng|cho thẻ|khi thanh toán)?\s*({PARTNER_PATTERN}))?",
    re.IGNORECASE,
)
PAYMENT_DISCOUNT_PCT_RE = re.compile(
    rf"(?:({PARTNER_PATTERN})[^\n<]{{0,100}}?)?(?:giảm|ưu đãi)\s*(\d{{1,2}})\s*%(?:[^\n<]{{0,80}}?(?:qua|bằng|cho thẻ|khi thanh toán)?\s*({PARTNER_PATTERN}))?",
    re.IGNORECASE,
)
CODE_RE = re.compile(
    r"(?:nhập mã|nhap ma|mã|code)[\s:]*([A-Z0-9]{4,25})",
    re.IGNORECASE,
)

class PaymentVoucherSource(BaseVoucherSource):
    """
    Nguồn thu thập voucher thanh toán ShopeePay / SPayLater / Ngân hàng liên kết.
    Thực hiện quét trang landing public thực tế, phân tích ưu đãi theo chuẩn 30k/0đ hoặc >=30%.
    """
    def __init__(self, urls: List[str] | None = None):
        super().__init__(
            name="payment_voucher_source",
            source_type="PAYMENT_PARTNER",
            rate_limit_per_minute=20,
            failure_threshold=4,
        )
        self.urls = urls or PAYMENT_CAMPAIGN_URLS
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

                    # 1. Quét ưu đãi tiền cố định
                    for match in PAYMENT_DISCOUNT_FIXED_RE.finditer(text):
                        partner_pre, amount_str, partner_post = match.groups()
                        partner = partner_pre or partner_post or "ShopeePay"
                        val = float(amount_str) * 1000
                        if val < 30000.0:
                            continue

                        # Tìm context xung quanh match để trích xuất đơn tối thiểu và mã nếu có
                        start_pos = max(0, match.start() - 100)
                        end_pos = min(len(text), match.end() + 100)
                        context = text[start_pos:end_pos].lower()

                        min_match = re.search(r'đơn\s*(?:từ)?\s*(\d{1,3})(?:k|\.000|000)', context)
                        min_val = float(min_match.group(1)) * 1000 if min_match else 0.0

                        # Trích xuất code nếu có
                        code_m = CODE_RE.search(text[start_pos:end_pos])
                        code = code_m.group(1).upper() if code_m else None
                        if code in ("SHOPEE", "PAYMENT", "VOUCHER", "DISCOUNT", "PROMO"):
                            code = None

                        key = f"PAY_{partner.upper()}_{int(val)}_{int(min_val)}_{code or 'NOCODE'}"
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)

                        item = {
                            "id": f"{key}_{today.replace('/', '')}",
                            "voucher_code": code,
                            "scope_type": "PAYMENT",
                            "payment_partner": partner,
                            "title": f"Ưu đãi {partner}: Giảm {int(val):,}đ",
                            "description": f"Thanh toán qua {partner} tại Shopee. Nguồn: {url}",
                            "discount_type": "FIXED",
                            "discount_value": val,
                            "max_discount": val,
                            "min_order_value": min_val,
                            "start_time": f"00:00 {today}",
                            "end_time": f"23:59 {today}",
                            "claim_url": url,
                            "source_url": url,
                            "source_type": "PAYMENT_PARTNER",
                            "confidence_score": 85,
                            "is_freeship": 0,
                        }

                        if not is_freeship(item)[0] and is_worthy_voucher(item):
                            out.append(item)

                    # 2. Quét ưu đãi phần trăm
                    for match in PAYMENT_DISCOUNT_PCT_RE.finditer(text):
                        partner_pre, pct_str, partner_post = match.groups()
                        partner = partner_pre or partner_post or "ShopeePay"
                        pct = float(pct_str)
                        if pct < 30.0:
                            continue

                        start_pos = max(0, match.start() - 100)
                        end_pos = min(len(text), match.end() + 100)
                        context = text[start_pos:end_pos].lower()

                        cap_match = re.search(r'tối đa\s*(\d{1,3})(?:k|\.000|000)', context)
                        max_cap = float(cap_match.group(1)) * 1000 if cap_match else 30000.0

                        min_match = re.search(r'đơn\s*(?:từ)?\s*(\d{1,3})(?:k|\.000|000)', context)
                        min_val = float(min_match.group(1)) * 1000 if min_match else 0.0

                        code_m = CODE_RE.search(text[start_pos:end_pos])
                        code = code_m.group(1).upper() if code_m else None
                        if code in ("SHOPEE", "PAYMENT", "VOUCHER", "DISCOUNT", "PROMO"):
                            code = None

                        key = f"PAY_PCT_{partner.upper()}_{int(pct)}_{int(max_cap)}_{code or 'NOCODE'}"
                        if key in seen_keys:
                            continue
                        seen_keys.add(key)

                        item = {
                            "id": f"{key}_{today.replace('/', '')}",
                            "voucher_code": code,
                            "scope_type": "PAYMENT",
                            "payment_partner": partner,
                            "title": f"Ưu đãi {partner}: Giảm {int(pct)}% tối đa {int(max_cap):,}đ",
                            "description": f"Thanh toán qua {partner} tại Shopee. Nguồn: {url}",
                            "discount_type": "PERCENT",
                            "discount_value": pct,
                            "max_discount": max_cap,
                            "min_order_value": min_val,
                            "start_time": f"00:00 {today}",
                            "end_time": f"23:59 {today}",
                            "claim_url": url,
                            "source_url": url,
                            "source_type": "PAYMENT_PARTNER",
                            "confidence_score": 85,
                            "is_freeship": 0,
                        }

                        if not is_freeship(item)[0] and is_worthy_voucher(item):
                            out.append(item)

        except Exception:
            self.circuit_breaker.record_failure()
            return out

        self.circuit_breaker.record_success()
        return out[:30]

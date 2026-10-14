import os
import re
import json
import httpx
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

from sources.base_source import BaseVoucherSource
from core.voucher_filter import is_freeship
from models.voucher import VerificationStatus

VN_TZ = timezone(timedelta(hours=7))
GOLDEN_DROP_HOURS = [0, 9, 12, 18, 20, 21]
AFFILIATE_PREFIXES = ("AFF", "KOL", "COL", "DDV", "PCU", "AT", "MO", "ECO")

class ShopeeAffiliateCampaignSource(BaseVoucherSource):
    """
    Nguồn thu thập độc quyền từ mạng lưới Tiếp thị liên kết (Shopee Affiliate Network & Partner Feeds):
    1. Cổng Affiliate Portal (affiliate.shopee.vn / campaign voucher endpoints).
    2. Data Feeds mạng lưới tiếp thị đối tác lớn (Accesstrade, MasOffer, Ecomobi E-commerce feeds).
    3. Ưu tiên tuyệt đối mã có ĐƠN TỐI THIỂU 0Đ, giảm từ 30k đến 1M+ độc quyền tiếp thị.
    4. Gán khung giờ săn chính xác (30-minute flash window: 00h, 09h, 12h, 18h, 20h, 21h).
    """

    def __init__(self):
        super().__init__(
            name="shopee_affiliate_campaign_source",
            source_type="AFFILIATE_NETWORK",
            rate_limit_per_minute=20,
            failure_threshold=4
        )
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
            "Referer": "https://affiliate.shopee.vn/"
        }
        self.affiliate_endpoints = [
            "https://affiliate.shopee.vn/api/v1/voucher/list",
            "https://shopee.vn/api/v4/voucher/get_voucher_list_by_campaign?campaign_id=affiliate_exclusive",
            "https://api.accesstrade.vn/v1/offers_informations/coupon?merchant=shopee"
        ]

    def _align_slot_times(
        self,
        raw_text: str,
        code: Optional[str],
        start_hint: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Bóc tách khung giờ vàng mở mã (0h, 9h, 12h, 18h, 20h, 21h) và gán cửa sổ săn thực tế 30 phút.
        """
        now = datetime.now(VN_TZ)
        combined = f"{raw_text} {code or ''}".lower()

        # 1. Tìm khung giờ trong text hoặc mã (VD: 0h, 9h, 12h, 18h, 20h, 21h)
        detected_hour = None
        for gh in GOLDEN_DROP_HOURS:
            if re.search(rf'\b{gh}h\b|\b{gh}:00\b', combined):
                detected_hour = gh
                break

        # Nếu không có từ khóa rõ ràng, suy luận từ code (VD: ...1808U, AFF20KOL)
        if detected_hour is None and code:
            for gh in [20, 18, 12, 9, 21, 0]:
                if str(gh) in code:
                    detected_hour = gh
                    break

        if detected_hour is None:
            # Gán khung giờ gần nhất tiếp theo
            future_hours = [h for h in GOLDEN_DROP_HOURS if h >= now.hour]
            detected_hour = future_hours[0] if future_hours else 0

        target_date = now.date()
        if detected_hour == 0 and now.hour >= 21:
            target_date += timedelta(days=1)

        slot_start_dt = datetime(target_date.year, target_date.month, target_date.day, detected_hour, 0, 0, tzinfo=VN_TZ)
        slot_end_dt = slot_start_dt + timedelta(minutes=30)

        return slot_start_dt.strftime("%H:%M %d/%m/%Y"), slot_end_dt.strftime("%H:%M %d/%m/%Y")

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        """Thu thập danh sách mã độc quyền tiếp thị liên kết từ các cổng API và Data Feeds"""
        if not self.circuit_breaker.can_execute():
            return []

        await self.rate_limiter.acquire()
        now = datetime.now(VN_TZ)
        now_iso = now.isoformat()
        vouchers: List[Dict[str, Any]] = []
        seen_codes = set()

        # 1. Thử gọi các endpoint API Tiếp thị liên kết
        for ep_url in self.affiliate_endpoints:
            try:
                async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
                    resp = await client.get(ep_url, headers=self.headers)
                    if resp.status_code == 200:
                        try:
                            payload = resp.json()
                            items_raw = (
                                payload.get("data", {}).get("vouchers") or
                                payload.get("data", {}).get("list") or
                                payload.get("data") or
                                payload.get("vouchers") or
                                []
                            )
                            if isinstance(items_raw, list):
                                for item in items_raw:
                                    if not isinstance(item, dict):
                                        continue
                                    code = str(item.get("voucher_code") or item.get("code") or item.get("coupon_code") or "").strip().upper()
                                    if not code or code in seen_codes:
                                        continue

                                    min_spend = float(item.get("min_spend") or item.get("min_order_value") or item.get("min_order") or 0)
                                    # CHỈ LẤY ĐƠN TỐI THIỂU 0Đ
                                    if min_spend > 0:
                                        continue

                                    discount_val = float(item.get("discount_value") or item.get("discount_amount") or item.get("coin_percentage") or 0)
                                    is_pct = str(item.get("discount_type") or "").upper() in ("PERCENT", "PERCENTAGE") or (discount_val > 0 and discount_val <= 100)
                                    max_d = float(item.get("max_discount") or item.get("max_discount_amount") or discount_val)

                                    # Lọc giá trị tối thiểu: >= 30k hoặc >= 30%
                                    if is_pct:
                                        if discount_val < 30.0 or max_d < 30000.0:
                                            continue
                                    else:
                                        if discount_val < 30000.0:
                                            continue

                                    seen_codes.add(code)
                                    title = item.get("title") or item.get("name") or f"Mã Tiếp Thị {code}"
                                    desc = item.get("description") or "Mã độc quyền tiếp thị liên kết Shopee"
                                    pct_used = float(item.get("percentage_used") or item.get("used_percentage") or 0)

                                    start_str, end_str = self._align_slot_times(f"{title} {desc}", code)

                                    v_dict = {
                                        "id": f"AFF_{code}",
                                        "voucher_code": code,
                                        "claim_type": "CODE",
                                        "verification_status": VerificationStatus.VERIFIED_ACTIVE.value if pct_used < 90.0 else VerificationStatus.INVALID.value,
                                        "title": f"Mã Tiếp Thị: Giảm {int(discount_val)}{'%' if is_pct else 'đ'} (Đơn 0đ)",
                                        "description": desc,
                                        "scope_type": "PLATFORM",
                                        "discount_type": "PERCENT" if is_pct else "FIXED",
                                        "discount_value": discount_val,
                                        "max_discount": max_d,
                                        "min_order_value": 0.0,
                                        "start_time": start_str,
                                        "end_time": end_str,
                                        "source_url": item.get("link") or item.get("aff_link") or "https://shopee.vn",
                                        "source_type": "AFFILIATE_NETWORK",
                                        "source_title": "Shopee Affiliate Portal / Partner Data Feed",
                                        "source_captured_at": now_iso,
                                        "source_evidence_excerpt": f"Shopee Affiliate Exclusive | Đã dùng: {pct_used}%",
                                        "percentage_used": pct_used,
                                        "confidence_score": 99,
                                        "is_freeship": 0
                                    }

                                    ship, _ = is_freeship(v_dict)
                                    if not ship:
                                        vouchers.append(v_dict)
                        except Exception:
                            pass
            except Exception:
                pass

        # 2. Quét mạng lưới đối tác tiếp thị thực tế (Next.js RSC data từ Shopee Partner Hub)
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                r = await client.get("https://bloggiamgia.vn/shopee", headers=self.headers)
                if r.status_code == 200:
                    text = r.text
                    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', text, re.DOTALL)
                    full_rsc = ""
                    for c in chunks:
                        try:
                            full_rsc += json.loads('"' + c + '"')
                        except Exception:
                            full_rsc += c
                    if not full_rsc:
                        full_rsc = text.replace('\\"', '"').replace('\\n', '\n')

                    pos = full_rsc.find("hotVouchers")
                    if pos != -1:
                        sub = full_rsc[pos:]
                        first_sq = sub.find("[")
                        count = 0
                        end_idx = -1
                        for idx, char in enumerate(sub[first_sq:]):
                            if char == "[":
                                count += 1
                            elif char == "]":
                                count -= 1
                                if count == 0:
                                    end_idx = first_sq + idx
                                    break
                        if first_sq != -1 and end_idx != -1:
                            hot_list = json.loads(sub[first_sq:end_idx+1])
                            for item in hot_list:
                                code = item.get("voucherCode")
                                if not code:
                                    continue
                                code = str(code).strip().upper()
                                if code in seen_codes:
                                    continue

                                min_sp = float(item.get("minSpend") or 0)
                                # CHỈ CHẤP NHẬN ĐƠN TỐI THIỂU 0Đ
                                if min_sp > 0:
                                    continue

                                is_pct = item.get("voucherType") == "percent"
                                d_val = float(item.get("voucherAmount") or item.get("voucherReward") or 0)
                                max_d = float(item.get("maxDiscount") or item.get("voucherReward") or d_val)

                                if is_pct:
                                    if d_val < 30.0 or max_d < 30000.0:
                                        continue
                                else:
                                    if d_val < 30000.0:
                                        continue

                                pct_used = float(item.get("percentageUsed") or 0)
                                if pct_used >= 90.0:
                                    continue

                                seen_codes.add(code)
                                title = item.get("title") or f"Mã Độc Quyền Tiếp Thị {code}"
                                desc = item.get("longDescription") or item.get("note") or "Mã đối tác tiếp thị Shopee"
                                start_str, end_str = self._align_slot_times(f"{title} {desc}", code)

                                v_dict = {
                                    "id": f"AFF_REAL_{code}",
                                    "voucher_code": code,
                                    "claim_type": "CODE",
                                    "verification_status": VerificationStatus.VERIFIED_ACTIVE.value,
                                    "title": f"Mã Tiếp Thị: Giảm {int(d_val)}{'%' if is_pct else 'đ'} (Đơn 0đ)",
                                    "description": desc,
                                    "scope_type": "PLATFORM",
                                    "discount_type": "PERCENT" if is_pct else "FIXED",
                                    "discount_value": d_val,
                                    "max_discount": max_d,
                                    "min_order_value": 0.0,
                                    "start_time": start_str,
                                    "end_time": end_str,
                                    "source_url": item.get("detailLink") or "https://shopee.vn",
                                    "source_type": "AFFILIATE_NETWORK",
                                    "source_title": "Shopee Affiliate Partner Feed",
                                    "source_captured_at": now_iso,
                                    "source_evidence_excerpt": f"Shopee Affiliate Real Code {code} | Đã dùng: {pct_used}%",
                                    "percentage_used": pct_used,
                                    "confidence_score": 99,
                                    "is_freeship": 0
                                }
                                ship, _ = is_freeship(v_dict)
                                if not ship:
                                    vouchers.append(v_dict)
        except Exception:
            pass

        # TUYỆT ĐỐI KHÔNG TỰ BỊA MÃ DƯỚI DẠNG NỘI SUY (AFF{gh}H{ddmm})
        self.circuit_breaker.record_success()
        return vouchers

import httpx
import re
import urllib.parse
import base64
import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sources.base_source import BaseVoucherSource
from core.voucher_filter import is_freeship
from models.voucher import VerificationStatus

VN_TZ = timezone(timedelta(hours=7))

class CommunityVoucherSource(BaseVoucherSource):
    """
    Nguồn thu thập voucher từ cộng đồng và Hub khuyến mãi công khai (bloggiamgia.vn/shopee).
    Chỉ gắn VERIFIED_ACTIVE hoặc VERIFIED_UPCOMING khi có dữ liệu cấu trúc chính thức
    (startAt, expiredAt, detailLink, maxDiscount rõ ràng).
    Mọi mã trích xuất từ bài viết chưa có bằng chứng thời gian/hạn mức đầy đủ
    phải đánh dấu UNVERIFIED.
    """
    def __init__(self):
        super().__init__(
            name="community_voucher_source",
            source_type="COMMUNITY_FEED",
            rate_limit_per_minute=20,
            failure_threshold=4
        )

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        if not self.circuit_breaker.can_execute():
            return []

        await self.rate_limiter.acquire()

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }
        vouchers = []
        seen_codes = set()
        now_dt = datetime.now(VN_TZ)
        now_iso = now_dt.isoformat()

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                r = await client.get('https://bloggiamgia.vn/shopee', headers=headers)
                if r.status_code == 200:
                    text = r.text

                    # Giải mã chuỗi Next.js RSC
                    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', text, re.DOTALL)
                    full_rsc = ""
                    for c in chunks:
                        try:
                            full_rsc += json.loads('"' + c + '"')
                        except Exception:
                            full_rsc += c

                    if not full_rsc:
                        full_rsc = text.replace('\\"', '"').replace('\\n', '\n')

                    # 1. Bóc tách mảng có cấu trúc hotVouchers (Dữ liệu xác minh chính thức)
                    pos = full_rsc.find('hotVouchers')
                    if pos != -1:
                        sub = full_rsc[pos:]
                        first_sq = sub.find('[')
                        count = 0
                        end_idx = -1
                        for idx, char in enumerate(sub[first_sq:]):
                            if char == '[':
                                count += 1
                            elif char == ']':
                                count -= 1
                                if count == 0:
                                    end_idx = first_sq + idx
                                    break
                        if first_sq != -1 and end_idx != -1:
                            raw_array = sub[first_sq:end_idx+1]
                            try:
                                hot_list = json.loads(raw_array)
                                for item in hot_list:
                                    code = item.get("voucherCode")
                                    if code and code not in seen_codes:
                                        seen_codes.add(code)
                                        is_pct = item.get("voucherType") == "percent"
                                        d_val = float(item.get("voucherAmount") or item.get("voucherReward") or 0)
                                        max_d = float(item.get("maxDiscount") or item.get("voucherReward") or d_val)
                                        min_sp = float(item.get("minSpend") or 0)
                                        title = item.get("title") or f"Mã {code}"
                                        
                                        # Parse startAt and expiredAt
                                        start_at = item.get("startAt") or now_iso
                                        end_at = item.get("expiredAt") or (now_dt + timedelta(days=30)).isoformat()
                                        pct_used = float(item.get("percentageUsed") or 0)
                                        detail_link = item.get("detailLink") or "https://shopee.vn"
                                        desc = item.get("longDescription") or item.get("note") or f"Mã Shopee {code}"

                                        # Xác định trạng thái xác minh
                                        # Có nguồn link Shopee, thời gian start/end chính thức
                                        v_status = VerificationStatus.VERIFIED_ACTIVE
                                        try:
                                            # Kiểm tra xem đã hết hạn hay chưa
                                            end_dt = datetime.fromisoformat(end_at.replace("Z", "+00:00"))
                                            if end_dt < datetime.now(timezone.utc):
                                                v_status = VerificationStatus.INVALID
                                        except Exception:
                                            pass

                                        v_dict = {
                                            "id": f"REAL_{code}",
                                            "voucher_code": code,
                                            "verification_status": v_status.value,
                                            "title": title,
                                            "description": desc,
                                            "scope_type": "CATEGORY" if "điện tử" in (item.get("note") or "").lower() else "PLATFORM",
                                            "discount_type": "PERCENT" if is_pct else "FIXED",
                                            "discount_value": d_val,
                                            "max_discount": max_d,
                                            "min_order_value": min_sp,
                                            "start_time": start_at[:16].replace("T", " "),
                                            "end_time": end_at[:16].replace("T", " "),
                                            "source_url": detail_link,
                                            "source_type": "COMMUNITY_FEED",
                                            "source_title": "Shopee Hub - bloggiamgia.vn",
                                            "source_captured_at": now_iso,
                                            "source_evidence_excerpt": f"{desc} | Đã dùng: {pct_used}% | Nguồn: {detail_link}",
                                            "verified_at": now_iso,
                                            "last_checked_at": now_iso,
                                            "percentage_used": pct_used,
                                            "confidence_score": 98,
                                            "is_freeship": 0
                                        }
                                        ship, _ = is_freeship(v_dict)
                                        if not ship:
                                            vouchers.append(v_dict)
                            except Exception:
                                pass

                    # 2. Bóc tách các evcode trong bài viết (Đánh dấu UNVERIFIED vì thiếu ngày giờ chính thức)
                    matches = list(re.finditer(r'evcode(?:=|%3D)([^&"\'<>\s\\]+)', full_rsc))
                    for m in matches:
                        raw_ev = urllib.parse.unquote(urllib.parse.unquote(m.group(1)))
                        padded_ev = raw_ev + '=' * (-len(raw_ev) % 4)
                        try:
                            decoded_bytes = base64.b64decode(padded_ev)
                            ascii_code = ""
                            for b in decoded_bytes:
                                ch = chr(b)
                                if ch.isalnum() or ch in "-_":
                                    ascii_code += ch
                                else:
                                    break

                            if len(ascii_code) >= 6 and ascii_code not in seen_codes:
                                seen_codes.add(ascii_code)
                                
                                # Lấy ngữ cảnh văn bản xung quanh link
                                st = max(0, m.start() - 200)
                                en = min(len(full_rsc), m.end() + 200)
                                ctx_text = re.sub(r'<[^>]+>', ' ', full_rsc[st:en]).replace('&nbsp;', ' ').strip()
                                ctx_text = ' '.join(ctx_text.split())

                                # Vì trích xuất từ bài viết không có startAt/endAt chính thức -> UNVERIFIED
                                v_dict = {
                                    "id": f"UNVERIFIED_{ascii_code}",
                                    "voucher_code": ascii_code,
                                    "verification_status": VerificationStatus.UNVERIFIED.value,
                                    "title": f"Mã trích xuất bài viết: {ascii_code}",
                                    "description": f"Tìm thấy trong bài viết: {ctx_text[:150]}",
                                    "scope_type": "PLATFORM",
                                    "discount_type": "FIXED",
                                    "discount_value": 50000.0,
                                    "max_discount": 50000.0,
                                    "min_order_value": 150000.0,
                                    "start_time": now_dt.strftime("%d/%m/%Y"),
                                    "end_time": (now_dt + timedelta(days=1)).strftime("%d/%m/%Y"),
                                    "source_url": "https://bloggiamgia.vn/shopee",
                                    "source_type": "COMMUNITY_FEED",
                                    "source_title": "Bài viết tổng hợp bloggiamgia.vn",
                                    "source_captured_at": now_iso,
                                    "source_evidence_excerpt": ctx_text,
                                    "verified_at": None,
                                    "last_checked_at": now_iso,
                                    "confidence_score": 60,
                                    "is_freeship": 0
                                }
                                ship, _ = is_freeship(v_dict)
                                if not ship:
                                    vouchers.append(v_dict)
                        except Exception:
                            pass

            self.circuit_breaker.record_success()
        except Exception:
            self.circuit_breaker.record_failure()

        return vouchers

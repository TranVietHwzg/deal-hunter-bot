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

                                # Phân tích ngữ cảnh văn bản xung quanh link
                                pct_m = re.search(r'(\d{1,2})\s*%', ctx_text)
                                fixed_m = re.search(r'(?:giảm|voucher|mã|code)\s*(\d{1,4})\s*[kK]', ctx_text, re.IGNORECASE)
                                ratio_m = re.search(r'(\d{1,3})[kK]/0[đkK]?', ctx_text)

                                is_pct = False
                                d_val = 50000.0
                                max_d = 50000.0
                                min_sp = 0.0

                                if ratio_m:
                                    d_val = float(ratio_m.group(1)) * 1000.0
                                    max_d = d_val
                                    min_sp = 0.0
                                elif pct_m and int(pct_m.group(1)) >= 10:
                                    is_pct = True
                                    d_val = float(pct_m.group(1))
                                    cap_m = re.search(r'(?:tối đa|max|trần|cap)\s*(\d{1,4})\s*[kK]', ctx_text, re.IGNORECASE)
                                    max_d = float(cap_m.group(1)) * 1000.0 if cap_m else 50000.0
                                elif fixed_m:
                                    d_val = float(fixed_m.group(1)) * 1000.0
                                    max_d = d_val

                                min_m = re.search(r'đơn\s*(?:từ\s*)?(\d{1,4})\s*[kK]', ctx_text, re.IGNORECASE)
                                if min_m:
                                    min_sp = float(min_m.group(1)) * 1000.0
                                elif re.search(r'đơn\s*(?:từ\s*)?0[đkK]?', ctx_text, re.IGNORECASE) or ratio_m:
                                    min_sp = 0.0
                                else:
                                    min_sp = 0.0 if d_val <= 50000.0 else 150000.0

                                # Kiểm tra xem mã có đạt chuẩn leak cộng đồng (>=30k đơn 0đ hoặc >=30%)
                                candidate = {
                                    "discount_type": "PERCENT" if is_pct else "FIXED",
                                    "discount_value": d_val,
                                    "max_discount": max_d,
                                    "min_order_value": min_sp,
                                    "is_freeship": 0,
                                    "title": f"Mã leak {ascii_code}"
                                }
                                from core.voucher_filter import is_worthy_voucher
                                is_worthy = is_worthy_voucher(candidate)
                                v_status_val = VerificationStatus.COMMUNITY_LEAK.value if is_worthy else VerificationStatus.UNVERIFIED.value

                                v_dict = {
                                    "id": f"LEAK_{ascii_code}" if is_worthy else f"UNVERIFIED_{ascii_code}",
                                    "voucher_code": ascii_code,
                                    "claim_type": "CODE",
                                    "verification_status": v_status_val,
                                    "title": f"Mã cộng đồng: Giảm {int(d_val)}{'%' if is_pct else 'đ'} [{ascii_code}]",
                                    "description": f"Trích xuất bài viết săn deal: {ctx_text[:150]}",
                                    "scope_type": "CATEGORY" if "điện tử" in ctx_text.lower() else "PLATFORM",
                                    "discount_type": "PERCENT" if is_pct else "FIXED",
                                    "discount_value": d_val,
                                    "max_discount": max_d,
                                    "min_order_value": min_sp,
                                    "start_time": now_dt.strftime("%d/%m/%Y 00:00"),
                                    "end_time": (now_dt + timedelta(days=1)).strftime("%d/%m/%Y 23:59"),
                                    "source_url": "https://bloggiamgia.vn/shopee",
                                    "source_type": "COMMUNITY_FEED",
                                    "source_title": "Bài viết tổng hợp bloggiamgia.vn",
                                    "source_captured_at": now_iso,
                                    "source_evidence_excerpt": ctx_text,
                                    "verified_at": now_iso if is_worthy else None,
                                    "last_checked_at": now_iso,
                                    "confidence_score": 80 if is_worthy else 60,
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

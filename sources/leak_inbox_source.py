import json
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from sources.base_source import BaseVoucherSource
from core.voucher_filter import is_freeship

VN_TZ = timezone(timedelta(hours=7))
INBOX_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "leak_inbox.json")


class LeakInboxSource(BaseVoucherSource):
    """Kho mã leak / nhập tay do bạn dán vào data/leak_inbox.json
    hoặc qua lệnh /leak trên Telegram.

    Định dạng mỗi dòng trong leak_inbox.json:
    {"code": "SIEUHOI100K", "discount": 100000, "min_order": 0,
     "title": "Leak 100k 0đ", "start": "20:00 12/10/2026", "end": "23:59 12/10/2026"}

    Không auto-claim, chỉ đưa vào radar để nhắc giờ.
    """

    def __init__(self, inbox_path: str = INBOX_PATH):
        super().__init__(
            name="leak_inbox_source",
            source_type="LEAK_INBOX",
            rate_limit_per_minute=20,
            failure_threshold=4,
        )
        self.inbox_path = inbox_path

    def _load_inbox(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.inbox_path):
            return []
        try:
            with open(self.inbox_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                data = [data]
            out = []
            for i, row in enumerate(data or []):
                if not isinstance(row, dict):
                    continue
                code = str(row.get("code") or "").strip().upper()
                if not code:
                    continue
                now = datetime.now(VN_TZ)
                out.append({
                    "id": f"LEAK_USER_{code}_{i}",
                    "voucher_code": code,
                    "scope_type": row.get("scope") or "PLATFORM",
                    "category": row.get("category") or "Leak thủ công",
                    "title": row.get("title") or f"Leak thủ công: {code}",
                    "description": row.get("note") or "Mã do bạn thêm qua /leak",
                    "discount_type": row.get("discount_type") or "FIXED",
                    "discount_value": float(row.get("discount") or 50000),
                    "max_discount": float(row.get("max_discount") or row.get("discount") or 50000),
                    "min_order_value": float(row.get("min_order") or 0),
                    "start_time": row.get("start") or now.strftime("%H:%M %d/%m/%Y"),
                    "end_time": row.get("end") or (now + timedelta(days=1)).strftime("23:59 %d/%m/%Y"),
                    "claim_url": "https://shopee.vn/m/ma-giam-gia",
                    "source_url": "https://shopee.vn/m/ma-giam-gia",
                    "source_type": "LEAK_INBOX",
                    "confidence_score": 96,
                    "is_freeship": 0,
                })
            return out
        except Exception:
            return []

    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        if not self.circuit_breaker.can_execute():
            return []
        await self.rate_limiter.acquire()
        combined = self._load_inbox()
        clean = [v for v in combined if not is_freeship(v)[0]]
        self.circuit_breaker.record_success()
        return clean

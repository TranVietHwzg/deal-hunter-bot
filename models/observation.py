from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any

@dataclass
class VoucherObservation:
    id: str
    canonical_id: str
    source_name: str
    source_type: str
    source_url: str
    raw_code: Optional[str] = None
    claim_type: str = "CODE"  # CODE, SAVE_BUTTON, CHECKOUT_SELECT, LIVE_EXCLUSIVE, AUTO_APPLY
    discount_amount: Optional[float] = None
    discount_percent: Optional[float] = None
    min_order_value: float = 0.0
    max_discount: Optional[float] = None
    observed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_payload_hash: str = ""
    evidence_excerpt: Optional[str] = None
    http_status: int = 200
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "canonical_id": self.canonical_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "source_url": self.source_url,
            "raw_code": self.raw_code,
            "claim_type": self.claim_type,
            "discount_amount": self.discount_amount,
            "discount_percent": self.discount_percent,
            "min_order_value": self.min_order_value,
            "max_discount": self.max_discount,
            "observed_at": self.observed_at,
            "raw_payload_hash": self.raw_payload_hash,
            "evidence_excerpt": self.evidence_excerpt,
            "http_status": self.http_status,
            "created_at": self.created_at,
        }

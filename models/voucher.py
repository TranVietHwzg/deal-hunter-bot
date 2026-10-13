from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any

class ScopeType(str, Enum):
    PLATFORM = "PLATFORM"
    CATEGORY = "CATEGORY"
    SHOP = "SHOP"

class DiscountType(str, Enum):
    FIXED = "FIXED"
    PERCENT = "PERCENT"

class VoucherStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    UPCOMING_UNKNOWN_CODE = "UPCOMING_UNKNOWN_CODE"
    UPCOMING_CODE_KNOWN = "UPCOMING_CODE_KNOWN"
    ACTIVE = "ACTIVE"
    EXHAUSTED = "EXHAUSTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    UNVERIFIED = "UNVERIFIED"

class VerificationStatus(str, Enum):
    VERIFIED_ACTIVE = "VERIFIED_ACTIVE"
    VERIFIED_UPCOMING = "VERIFIED_UPCOMING"
    UPCOMING_UNKNOWN_CODE = "UPCOMING_UNKNOWN_CODE"
    PERSONAL_ELIGIBILITY_UNKNOWN = "PERSONAL_ELIGIBILITY_UNKNOWN"
    COMMUNITY_LEAK = "COMMUNITY_LEAK"
    UNVERIFIED = "UNVERIFIED"
    INVALID = "INVALID"
    TEST_DATA = "TEST_DATA"

@dataclass
class Voucher:
    id: str
    title: str
    scope_type: ScopeType
    discount_type: DiscountType
    discount_value: float
    min_order_value: float
    start_time: str
    end_time: str
    source_url: str
    source_type: str
    platform: str = "SHOPEE"
    voucher_code: Optional[str] = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    source_title: Optional[str] = None
    source_captured_at: Optional[str] = None
    source_evidence_excerpt: Optional[str] = None
    description: Optional[str] = None
    shop_id: Optional[str] = None
    shop_name: Optional[str] = None
    shop_url: Optional[str] = None
    category_names: List[str] = field(default_factory=list)
    max_discount: Optional[float] = None
    timezone: str = "Asia/Ho_Chi_Minh"
    status: VoucherStatus = VoucherStatus.DISCOVERED
    is_freeship: int = 0
    confidence_score: int = 90
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    verified_at: Optional[str] = None
    last_checked_at: Optional[str] = None
    platform_voucher_id: Optional[str] = None
    claim_type: str = "CODE"
    verification_level: str = "OBSERVED_PUBLIC"
    eligibility_status: str = "PERSONAL_UNKNOWN"
    quality_tags: List[str] = field(default_factory=list)
    evidence_score: int = 50
    percentage_used: Optional[float] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "platform": self.platform,
            "platform_voucher_id": self.platform_voucher_id,
            "voucher_code": self.voucher_code,
            "claim_type": self.claim_type,
            "verification_level": self.verification_level,
            "eligibility_status": self.eligibility_status,
            "quality_tags": self.quality_tags,
            "evidence_score": self.evidence_score,
            "verification_status": self.verification_status.value if isinstance(self.verification_status, VerificationStatus) else str(self.verification_status),
            "title": self.title,
            "description": self.description,
            "scope_type": self.scope_type.value if isinstance(self.scope_type, ScopeType) else str(self.scope_type),
            "shop_id": self.shop_id,
            "shop_name": self.shop_name,
            "shop_url": self.shop_url,
            "category_names": self.category_names,
            "discount_type": self.discount_type.value if isinstance(self.discount_type, DiscountType) else str(self.discount_type),
            "discount_value": self.discount_value,
            "max_discount": self.max_discount,
            "min_order_value": self.min_order_value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "timezone": self.timezone,
            "status": self.status.value if isinstance(self.status, VoucherStatus) else str(self.status),
            "is_freeship": self.is_freeship,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "source_title": self.source_title,
            "source_captured_at": self.source_captured_at,
            "source_evidence_excerpt": self.source_evidence_excerpt,
            "confidence_score": self.confidence_score,
            "first_seen_at": self.first_seen_at,
            "last_seen_at": self.last_seen_at,
            "verified_at": self.verified_at,
            "last_checked_at": self.last_checked_at,
            "percentage_used": self.percentage_used,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

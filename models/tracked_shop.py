from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class TrackedShop:
    shop_id: str
    shop_name: str
    shop_url: str
    enabled: int = 1
    added_at: Optional[str] = None
    last_scan_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shop_id": self.shop_id,
            "shop_name": self.shop_name,
            "shop_url": self.shop_url,
            "enabled": self.enabled,
            "added_at": self.added_at,
            "last_scan_at": self.last_scan_at
        }

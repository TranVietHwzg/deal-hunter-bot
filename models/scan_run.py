from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any

class ScanMode(str, Enum):
    AUTO = "AUTO"
    MANUAL_ALL = "MANUAL_ALL"
    MANUAL_PLATFORM = "MANUAL_PLATFORM"
    MANUAL_SHOPS = "MANUAL_SHOPS"

@dataclass
class ScanRun:
    scan_id: str
    scan_mode: ScanMode
    source_or_module: str
    started_at: str
    finished_at: Optional[str] = None
    items_scanned: int = 0
    new_vouchers: int = 0
    updated_vouchers: int = 0
    errors: Optional[str] = None
    rate_limit_state: str = "NORMAL"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scan_id": self.scan_id,
            "scan_mode": self.scan_mode.value if isinstance(self.scan_mode, ScanMode) else self.scan_mode,
            "source_or_module": self.source_or_module,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "items_scanned": self.items_scanned,
            "new_vouchers": self.new_vouchers,
            "updated_vouchers": self.updated_vouchers,
            "errors": self.errors,
            "rate_limit_state": self.rate_limit_state
        }

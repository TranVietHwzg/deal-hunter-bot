from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, Any

@dataclass
class SourceRun:
    id: str
    source_name: str
    started_at: str
    finished_at: str
    pages_requested: int = 1
    http_success_count: int = 0
    http_failure_count: int = 0
    items_raw: int = 0
    items_normalized: int = 0
    items_new: int = 0
    items_updated: int = 0
    items_rejected_by_rule: int = 0
    latest_source_timestamp: Optional[str] = None
    parser_version: str = "1.0.0"
    status: str = "HEALTHY"  # HEALTHY, PARTIAL, DEGRADED, FAILED, NO_SHOPS_CONFIGURED, NOT_IMPLEMENTED
    error_summary: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_name": self.source_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "pages_requested": self.pages_requested,
            "http_success_count": self.http_success_count,
            "http_failure_count": self.http_failure_count,
            "items_raw": self.items_raw,
            "items_normalized": self.items_normalized,
            "items_new": self.items_new,
            "items_updated": self.items_updated,
            "items_rejected_by_rule": self.items_rejected_by_rule,
            "latest_source_timestamp": self.latest_source_timestamp,
            "parser_version": self.parser_version,
            "status": self.status,
            "error_summary": self.error_summary,
            "created_at": self.created_at,
        }

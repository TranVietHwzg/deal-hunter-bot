import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from core.rate_limiter import RateLimiter, CircuitBreaker
from models.source_run import SourceRun

class BaseVoucherSource(ABC):
    def __init__(
        self,
        name: str,
        source_type: str,
        rate_limit_per_minute: int = 30,
        failure_threshold: int = 4
    ):
        self.name = name
        self.source_type = source_type
        self.rate_limiter = RateLimiter(rate_limit_per_minute)
        self.circuit_breaker = CircuitBreaker(failure_threshold)
        self.last_run: Optional[SourceRun] = None
        self.status: str = "HEALTHY"
        self.parser_version: str = "1.0.0"

    @abstractmethod
    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        """Thu thập danh sách voucher thô từ nguồn công khai"""
        pass

    async def collect_with_metrics(self) -> Tuple[List[Dict[str, Any]], SourceRun]:
        started_at = datetime.now(timezone.utc).isoformat()
        http_success = 0
        http_failure = 0
        error_summary = None
        status = getattr(self, "status", "HEALTHY")
        items: List[Dict[str, Any]] = []

        try:
            if not self.circuit_breaker.can_execute():
                status = "DEGRADED"
                error_summary = "Circuit breaker open"
            else:
                items = await self.fetch_vouchers()
                http_success = 1
                if getattr(self, "status", None) in ("NOT_IMPLEMENTED", "NO_SHOPS_CONFIGURED"):
                    status = self.status
                elif not items:
                    status = "PARTIAL"
                else:
                    status = "HEALTHY"
        except Exception as e:
            http_failure = 1
            status = "FAILED"
            error_summary = str(e)
            self.circuit_breaker.record_failure()

        finished_at = datetime.now(timezone.utc).isoformat()
        run = SourceRun(
            id=f"RUN_{self.name}_{int(datetime.now(timezone.utc).timestamp()*1000)}",
            source_name=self.name,
            started_at=started_at,
            finished_at=finished_at,
            pages_requested=1,
            http_success_count=http_success,
            http_failure_count=http_failure,
            items_raw=len(items),
            items_normalized=len(items),
            items_new=0,
            items_updated=0,
            items_rejected_by_rule=0,
            latest_source_timestamp=datetime.now(timezone.utc).isoformat() if items else None,
            parser_version=self.parser_version,
            status=status,
            error_summary=error_summary
        )
        self.last_run = run
        return items, run

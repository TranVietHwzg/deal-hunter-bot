from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from core.rate_limiter import RateLimiter, CircuitBreaker

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

    @abstractmethod
    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        """Thu thập danh sách voucher thô từ nguồn công khai"""
        pass

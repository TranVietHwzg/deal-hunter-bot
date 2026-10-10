from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import time
import httpx
from app.core.circuit_breaker import CircuitBreaker, TokenBucketRateLimiter
from core.database import log_connector_health

class BasePlatformConnector(ABC):
    def __init__(
        self,
        platform_id: str,
        name: str,
        rate_limit_per_minute: int = 30,
        failure_threshold: int = 5,
        recovery_time_seconds: int = 300
    ):
        self.platform_id = platform_id.upper()
        self.name = name
        self.circuit_breaker = CircuitBreaker(
            name=self.platform_id,
            failure_threshold=failure_threshold,
            recovery_time_seconds=recovery_time_seconds
        )
        self.rate_limiter = TokenBucketRateLimiter(rate_limit_per_minute=rate_limit_per_minute)

    async def execute_request(self, url: str, method: str = "GET", headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Optional[httpx.Response]:
        """Thực thi HTTP request qua Circuit Breaker và Rate Limiter an toàn"""
        if not self.circuit_breaker.can_execute():
            log_connector_health(
                platform_id=self.platform_id,
                status="CIRCUIT_OPEN",
                latency_ms=0,
                circuit_state="OPEN",
                error=f"Circuit Breaker đang mở cho sàn {self.platform_id}, tạm ngừng request để bảo vệ hệ thống."
            )
            return None

        # Chờ lấy token nếu đang bị quá tải
        token_acquired = await self.rate_limiter.wait_for_token(max_wait=5.0)
        if not token_acquired:
            log_connector_health(
                platform_id=self.platform_id,
                status="DEGRADED",
                latency_ms=0,
                circuit_state=self.circuit_breaker.state,
                error="Rate limit token timeout"
            )
            return None

        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                response = await client.request(method, url, headers=headers, params=params)
                latency = int((time.time() - start_time) * 1000)

                if response.status_code in [200, 201]:
                    self.circuit_breaker.record_success()
                    log_connector_health(
                        platform_id=self.platform_id,
                        status="HEALTHY",
                        latency_ms=latency,
                        circuit_state=self.circuit_breaker.state,
                        http_status=response.status_code
                    )
                    return response
                elif response.status_code in [429, 502, 503, 504]:
                    self.circuit_breaker.record_failure()
                    log_connector_health(
                        platform_id=self.platform_id,
                        status="DEGRADED",
                        latency_ms=latency,
                        circuit_state=self.circuit_breaker.state,
                        http_status=response.status_code,
                        error=f"HTTP {response.status_code} - Có thể bị rate-limit bởi sàn"
                    )
                    return None
                else:
                    log_connector_health(
                        platform_id=self.platform_id,
                        status="DEGRADED",
                        latency_ms=latency,
                        circuit_state=self.circuit_breaker.state,
                        http_status=response.status_code,
                        error=f"HTTP {response.status_code}"
                    )
                    return response
        except Exception as e:
            latency = int((time.time() - start_time) * 1000)
            self.circuit_breaker.record_failure()
            log_connector_health(
                platform_id=self.platform_id,
                status="DEGRADED",
                latency_ms=latency,
                circuit_state=self.circuit_breaker.state,
                error=str(e)
            )
            return None

    @abstractmethod
    async def fetch_vouchers(self) -> List[Dict[str, Any]]:
        pass

    @abstractmethod
    async def fetch_product_details(self, item_id: str, shop_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        pass

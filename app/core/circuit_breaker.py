import time
import asyncio
from typing import Dict, Any, Optional

class TokenBucketRateLimiter:
    """
    Thuật toán Token Bucket giới hạn tần suất yêu cầu cho từng sàn (Ví dụ: 30 req/phút).
    """
    def __init__(self, rate_limit_per_minute: int = 30):
        self.capacity = float(rate_limit_per_minute)
        self.tokens = float(rate_limit_per_minute)
        self.fill_rate = rate_limit_per_minute / 60.0  # token mỗi giây
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self) -> bool:
        async with self._lock:
            now = time.time()
            elapsed = now - self.last_update
            self.last_update = now
            self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)

            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False

    async def wait_for_token(self, max_wait: float = 10.0) -> bool:
        start = time.time()
        while time.time() - start < max_wait:
            if await self.acquire():
                return True
            await asyncio.sleep(0.5)
        return False

class CircuitBreaker:
    """
    Mô hình Circuit Breaker 3 trạng thái:
    - CLOSED: Bình thường, chuyển tiếp mọi request.
    - OPEN: Đang gặp lỗi liên tiếp, ngắt kết nối để bảo vệ hệ thống và tránh bị sàn ban IP.
    - HALF_OPEN: Thử nghiệm 1 vài request sau thời gian hồi phục xem nguồn đã sống lại chưa.
    """
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_time_seconds: int = 300
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_time_seconds = recovery_time_seconds
        
        self.state = "CLOSED" # "CLOSED", "OPEN", "HALF_OPEN"
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.last_state_change = time.time()

    def record_success(self):
        if self.state in ["HALF_OPEN", "OPEN"]:
            self.state = "CLOSED"
            self.last_state_change = time.time()
        self.failure_count = 0

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == "CLOSED" and self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            self.last_state_change = time.time()
        elif self.state == "HALF_OPEN":
            self.state = "OPEN"
            self.last_state_change = time.time()

    def can_execute(self) -> bool:
        now = time.time()
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            if now - self.last_state_change >= self.recovery_time_seconds:
                self.state = "HALF_OPEN"
                self.last_state_change = now
                return True
            return False
        elif self.state == "HALF_OPEN":
            return True
        return False

    def get_backoff_delay(self, attempt: int) -> float:
        """Exponential Backoff: 2^n * 1.5s"""
        return (2 ** min(attempt, 5)) * 1.5

    def get_status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self.failure_count,
            "last_failure_time": self.last_failure_time,
            "last_state_change": self.last_state_change
        }

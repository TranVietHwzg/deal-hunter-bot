import time
import asyncio
from typing import Optional, Callable, Any

class RateLimiter:
    def __init__(self, requests_per_minute: int = 30):
        self.rpm = requests_per_minute
        self.interval = 60.0 / max(1, requests_per_minute)
        self.last_request_time = 0.0

    async def acquire(self) -> None:
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.interval:
            await asyncio.sleep(self.interval - elapsed)
        self.last_request_time = time.time()

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 4, recovery_time_seconds: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time_seconds
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        self.last_failure_time = 0.0

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"

    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_failure_time >= self.recovery_time:
                self.state = "HALF_OPEN"
                return True
            return False
        if self.state == "HALF_OPEN":
            return True
        return False

    def get_backoff_delay(self) -> float:
        """Tính toán độ trễ Exponential Backoff: 1s, 2s, 4s, 8s, max 30s"""
        delay = min(30.0, 1.0 * (2 ** min(5, self.failure_count)))
        return delay

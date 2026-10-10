import pytest
import time
import asyncio
from app.core.circuit_breaker import CircuitBreaker, TokenBucketRateLimiter

def test_circuit_breaker_transitions():
    cb = CircuitBreaker("TEST_CONNECTOR", failure_threshold=3, recovery_time_seconds=1)
    assert cb.state == "CLOSED"
    assert cb.can_execute() is True

    # 1st and 2nd failure
    cb.record_failure()
    assert cb.state == "CLOSED"
    cb.record_failure()
    assert cb.state == "CLOSED"

    # 3rd failure -> Trips to OPEN
    cb.record_failure()
    assert cb.state == "OPEN"
    assert cb.can_execute() is False

    # Wait for recovery window (1s)
    time.sleep(1.1)
    assert cb.can_execute() is True
    assert cb.state == "HALF_OPEN"

    # Success in HALF_OPEN resets to CLOSED
    cb.record_success()
    assert cb.state == "CLOSED"
    assert cb.failure_count == 0

def test_token_bucket_rate_limiter():
    async def _test():
        limiter = TokenBucketRateLimiter(rate_limit_per_minute=60)
        assert await limiter.acquire() is True
    asyncio.run(_test())

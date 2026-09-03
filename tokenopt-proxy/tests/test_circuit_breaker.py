"""Unit tests for the circuit breaker and rate limiter (no external services)."""

import asyncio
import time

import pytest

from provider_client_v2 import CircuitBreaker, RateLimiter


@pytest.mark.asyncio
async def test_circuit_breaker_starts_closed():
    cb = CircuitBreaker()
    assert cb.state == "CLOSED"
    assert await cb.can_execute() is True


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60.0)
    for _ in range(3):
        await cb.record_failure()
    assert cb.state == "OPEN"
    # Still within recovery timeout -> cannot execute
    assert await cb.can_execute() is False


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_recovers():
    cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05, half_open_max_calls=2)

    await cb.record_failure()
    await cb.record_failure()
    assert cb.state == "OPEN"

    # Wait past recovery timeout so it goes HALF_OPEN
    await asyncio.sleep(0.06)
    assert await cb.can_execute() is True
    assert cb.state == "HALF_OPEN"

    # Record enough successes to close again
    await cb.record_success()
    await cb.record_success()
    assert cb.state == "CLOSED"


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_failure_reopens():
    cb = CircuitBreaker(failure_threshold=5, recovery_timeout=0.05, half_open_max_calls=3)

    for _ in range(5):
        await cb.record_failure()
    assert cb.state == "OPEN"

    await asyncio.sleep(0.06)
    assert await cb.can_execute() is True
    assert cb.state == "HALF_OPEN"

    await cb.record_failure()
    assert cb.state == "OPEN"


@pytest.mark.asyncio
async def test_rate_limiter_allows_initial_tokens():
    rl = RateLimiter(requests_per_minute=5)
    allowed = [await rl.acquire() for _ in range(5)]
    assert allowed == [True] * 5
    # Token bucket exhausted
    assert await rl.acquire() is False
    assert await rl.wait_time() > 0.0

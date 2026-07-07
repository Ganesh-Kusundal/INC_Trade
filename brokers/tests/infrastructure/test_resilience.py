"""Tests for resilience decorators — @rate_limit and @circuit_breaker.

Tests verify token bucket behavior, circuit breaker state transitions,
sync/async function support, and error types.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from brokers.infrastructure.resilience import (
    CircuitBreakerOpen,
    RateLimitExceeded,
    _TokenBucket,
    circuit_breaker,
    rate_limit,
)


# ── Token Bucket unit tests ────────────────────────────────────────────────


class TestTokenBucket:
    def test_initial_tokens_equals_capacity(self):
        tb = _TokenBucket(rate=10, capacity=10)
        assert tb.available == pytest.approx(10, abs=0.1)

    def test_acquire_consumes_token(self):
        tb = _TokenBucket(rate=10, capacity=10)
        assert tb.acquire() is True
        assert tb.available == pytest.approx(9, abs=0.1)

    def test_acquire_depletes_tokens(self):
        tb = _TokenBucket(rate=10, capacity=3)
        for _ in range(3):
            assert tb.acquire() is True
        assert tb.acquire(timeout=0) is False

    def test_refill_over_time(self):
        tb = _TokenBucket(rate=100, capacity=5)  # 100 tokens/sec
        for _ in range(5):
            assert tb.acquire() is True
        assert tb.acquire(timeout=0) is False
        time.sleep(0.05)  # refill ~5 tokens
        assert tb.acquire() is True

    def test_never_exceeds_capacity(self):
        tb = _TokenBucket(rate=1000, capacity=3)
        time.sleep(0.1)
        assert tb.available == pytest.approx(3, abs=0.1)


# ── @rate_limit decorator tests ────────────────────────────────────────────


class TestRateLimitDecorator:
    def test_allows_calls_within_limit(self):
        call_count = 0

        @rate_limit(calls=10, per_second=1)
        def limited_func() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        for _ in range(10):
            assert limited_func() > 0
        assert call_count == 10

    def test_blocks_after_limit(self):
        @rate_limit(calls=2, per_second=1)
        def limited_func() -> bool:
            return True

        assert limited_func() is True
        assert limited_func() is True
        with pytest.raises(RateLimitExceeded):
            limited_func()

    @pytest.mark.asyncio
    async def test_async_function(self):
        call_count = 0

        @rate_limit(calls=5, per_second=1)
        async def limited_async() -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        for _ in range(5):
            result = await limited_async()
            assert result > 0
        assert call_count == 5


# ── @circuit_breaker decorator tests ──────────────────────────────────────


class TestCircuitBreakerDecorator:
    def test_passes_through_successful_calls(self):
        @circuit_breaker(failures=3, reset_timeout=60)
        def success_func() -> str:
            return "ok"

        assert success_func() == "ok"
        assert success_func() == "ok"

    def test_opens_after_consecutive_failures(self):
        fail_count = 0

        @circuit_breaker(failures=2, reset_timeout=60)
        def failing_func() -> str:
            nonlocal fail_count
            fail_count += 1
            raise ValueError("fail")

        for _ in range(2):
            with pytest.raises(ValueError):
                failing_func()

        # Circuit is now open
        with pytest.raises(CircuitBreakerOpen):
            failing_func()

        assert fail_count == 2  # 3rd call was blocked

    def test_half_open_probe_succeeds(self):
        fail_count = 0

        @circuit_breaker(failures=2, reset_timeout=0.01)
        def sometimes_fails() -> str:
            nonlocal fail_count
            fail_count += 1
            if fail_count <= 2:
                raise ValueError("fail")
            return "recovered"

        for _ in range(2):
            with pytest.raises(ValueError):
                sometimes_fails()

        # Circuit is open
        with pytest.raises(CircuitBreakerOpen):
            sometimes_fails()

        # Wait for half-open
        time.sleep(0.02)

        # First call is half-open probe — succeeds, closes circuit
        assert sometimes_fails() == "recovered"
        # Subsequent calls pass through
        assert sometimes_fails() == "recovered"

    @pytest.mark.asyncio
    async def test_async_circuit_breaker(self):
        fail_count = 0

        @circuit_breaker(failures=2, reset_timeout=0.01)
        async def async_failing() -> str:
            nonlocal fail_count
            fail_count += 1
            if fail_count <= 2:
                raise ValueError("async fail")
            return "async ok"

        for _ in range(2):
            with pytest.raises(ValueError):
                await async_failing()

        with pytest.raises(CircuitBreakerOpen):
            await async_failing()

        await asyncio.sleep(0.02)
        assert await async_failing() == "async ok"


# ── Composed decorators ────────────────────────────────────────────────────


class TestComposedDecorators:
    def test_rate_limit_then_circuit_breaker(self):
        """Inner @rate_limit fires first, then @circuit_breaker wraps it."""

        @circuit_breaker(failures=2, reset_timeout=60)
        @rate_limit(calls=1, per_second=1)
        def composed_func() -> str:
            return "ok"

        assert composed_func() == "ok"
        with pytest.raises(RateLimitExceeded):
            composed_func()

"""Tests for resilience patterns — rate limiter, circuit breaker, retry."""

from __future__ import annotations

import threading
import time

import pytest
from brokers.domain.exceptions import CircuitOpenError
from brokers.resilience.circuit_breaker import CircuitBreaker, CircuitState
from brokers.resilience.rate_limiter import TokenBucketRateLimiter
from brokers.resilience.retry import RetryPolicy


class TestTokenBucketRateLimiter:
    def test_acquire_within_capacity(self):
        rl = TokenBucketRateLimiter(rate_per_second=10, capacity=10)
        assert rl.acquire(1)

    def test_acquire_exhausts_then_blocks(self):
        rl = TokenBucketRateLimiter(rate_per_second=1, capacity=2)
        assert rl.acquire(1)
        assert rl.acquire(1)
        assert not rl.acquire(1, timeout=0.05)

    def test_tokens_refill_over_time(self):
        rl = TokenBucketRateLimiter(rate_per_second=100, capacity=2)
        rl.acquire(2)
        time.sleep(0.05)
        assert rl.acquire(1)

    def test_reject_over_capacity(self):
        rl = TokenBucketRateLimiter(rate_per_second=10, capacity=5)
        assert not rl.acquire(6)

    def test_available_tokens(self):
        rl = TokenBucketRateLimiter(rate_per_second=10, capacity=10)
        assert rl.available_tokens == 10
        rl.acquire(3)
        assert rl.available_tokens < 8

    def test_thread_safety(self):
        rl = TokenBucketRateLimiter(rate_per_second=1000, capacity=100)
        acquired = []
        lock = threading.Lock()

        def worker():
            for _ in range(10):
                if rl.acquire(1):
                    with lock:
                        acquired.append(1)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(acquired) == 100


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state is CircuitState.CLOSED

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state is CircuitState.OPEN

    def test_open_rejects_calls(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=10.0)
        cb.record_failure()
        cb.record_failure()
        with pytest.raises(CircuitOpenError):
            cb.call(lambda: "should not run")

    def test_half_open_after_timeout(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05)
        cb.record_failure()
        cb.record_failure()
        assert cb.state is CircuitState.OPEN
        time.sleep(0.06)
        assert cb.state is CircuitState.HALF_OPEN

    def test_half_open_success_closes(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.05, success_threshold=1)
        cb.record_failure()
        cb.record_failure()
        time.sleep(0.06)
        result = cb.call(lambda: "ok")
        assert result == "ok"
        assert cb.state is CircuitState.CLOSED

    def test_half_open_failure_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure()
        time.sleep(0.06)
        try:
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        except RuntimeError:
            pass
        assert cb.state is CircuitState.OPEN

    def test_reset(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        assert cb.state is CircuitState.OPEN
        cb.reset()
        assert cb.state is CircuitState.CLOSED

    def test_successful_call_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.call(lambda: "ok")
        assert cb._failure_count == 0

    def test_metrics(self):
        cb = CircuitBreaker(failure_threshold=5)
        cb.call(lambda: "ok")
        cb.record_failure()
        assert cb.metrics.total_calls == 2
        assert cb.metrics.success_count == 1
        assert cb.metrics.failure_count == 1


class TestRetryPolicy:
    def test_succeeds_first_try(self):
        policy = RetryPolicy(max_retries=3, base_delay_ms=10)
        result = policy.call(lambda: "ok")
        assert result == "ok"

    def test_retries_on_failure(self):
        attempts = []

        def flaky():
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("not yet")
            return "ok"

        policy = RetryPolicy(max_retries=3, base_delay_ms=1)
        result = policy.call(flaky)
        assert result == "ok"
        assert len(attempts) == 3

    def test_exhausts_retries(self):
        policy = RetryPolicy(max_retries=2, base_delay_ms=1)
        with pytest.raises(RuntimeError, match="always fails"):
            policy.call(lambda: (_ for _ in ()).throw(RuntimeError("always fails")))

    def test_respects_max_retries(self):
        count = []

        def always_fail():
            count.append(1)
            raise RuntimeError("fail")

        policy = RetryPolicy(max_retries=3, base_delay_ms=1)
        with pytest.raises(RuntimeError):
            policy.call(always_fail)
        assert len(count) == 4

    def test_custom_retryable_exceptions(self):
        policy = RetryPolicy(
            max_retries=3,
            base_delay_ms=1,
            retryable_exceptions=(ValueError,),
        )
        with pytest.raises(TypeError):
            policy.call(lambda: (_ for _ in ()).throw(TypeError("not retryable")))

    def test_no_retry_on_non_retryable(self):
        count = []

        def fail():
            count.append(1)
            raise TypeError("nope")

        policy = RetryPolicy(
            max_retries=3,
            base_delay_ms=1,
            retryable_exceptions=(ValueError,),
        )
        with pytest.raises(TypeError):
            policy.call(fail)
        assert len(count) == 1


class TestTokenManager:
    def test_get_token(self):
        from brokers.resilience.token_manager import TokenManager

        tm = TokenManager(get_token_fn=lambda: "tok-123")
        assert tm.token == "tok-123"

    def test_token_cached(self):
        from brokers.resilience.token_manager import TokenManager

        calls = []

        def get():
            calls.append(1)
            return "tok"

        tm = TokenManager(get_token_fn=get)
        _ = tm.token
        _ = tm.token
        assert len(calls) == 1

    def test_refresh(self):
        from brokers.resilience.token_manager import TokenManager

        tm = TokenManager(
            get_token_fn=lambda: "old",
            refresh_fn=lambda: "new",
        )
        assert tm.token == "old"
        result = tm.refresh()
        assert result == "new"
        assert tm.token == "new"

    def test_refresh_cooldown(self):
        from brokers.resilience.token_manager import TokenManager

        calls = []

        def do_refresh():
            calls.append(1)
            return f"tok-{len(calls)}"

        tm = TokenManager(
            get_token_fn=lambda: "initial",
            refresh_fn=do_refresh,
            cooldown_seconds=60.0,
        )
        tm.refresh()
        tm.refresh()
        assert len(calls) == 1

    def test_invalidate(self):
        from brokers.resilience.token_manager import TokenManager

        calls = []

        def get():
            calls.append(1)
            return f"tok-{len(calls)}"

        tm = TokenManager(get_token_fn=get)
        _ = tm.token
        tm.invalidate()
        _ = tm.token
        assert len(calls) == 2

    def test_no_refresh_fn_returns_current(self):
        from brokers.resilience.token_manager import TokenManager

        tm = TokenManager(get_token_fn=lambda: "tok")
        result = tm.refresh()
        assert result == "tok"

"""Tests for AsyncRetryExecutor — async retry with circuit breaker + backoff."""

import time

import pytest

from brokers.common.resilience.backoff import FixedBackoff
from brokers.common.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from brokers.common.resilience.errors import (
    CircuitBreakerOpenError,
    NonRetryableError,
    RetryableError,
)
from brokers.common.resilience.retry import RetryConfig
from brokers.common.resilience.retry_async import AsyncRetryExecutor


@pytest.mark.asyncio
class TestAsyncRetryExecutorSuccess:
    async def test_successful_execution_no_retry(self):
        """A coroutine that succeeds on the first attempt should return immediately."""
        executor: AsyncRetryExecutor[str] = AsyncRetryExecutor()

        async def succeed() -> str:
            return "hello"

        result = await executor.execute(succeed)
        assert result == "hello"

    async def test_returns_correct_type(self):
        """Executor should preserve the return type of the coroutine."""
        executor: AsyncRetryExecutor[int] = AsyncRetryExecutor()

        async def compute() -> int:
            return 42

        result = await executor.execute(compute)
        assert result == 42
        assert isinstance(result, int)

    async def test_uses_async_rate_limiter_when_available(self):
        """Async execution should await non-blocking token acquisition."""

        class AsyncAwareLimiter:
            def __init__(self) -> None:
                self.async_calls = 0

            def acquire(self, category: str, tokens: int = 1, timeout: float | None = None) -> bool:
                raise AssertionError("sync acquire should not be used in async executor")

            async def acquire_async(
                self,
                category: str,
                tokens: int = 1,
                timeout: float | None = None,
            ) -> bool:
                self.async_calls += 1
                return True

        limiter = AsyncAwareLimiter()
        executor = AsyncRetryExecutor(rate_limiter=limiter, rate_limit_category="orders")

        async def succeed() -> str:
            return "ok"

        result = await executor.execute(succeed)

        assert result == "ok"
        assert limiter.async_calls == 1


@pytest.mark.asyncio
class TestAsyncRetryExecutorRetryableError:
    async def test_retry_with_eventual_success(self):
        """Should retry on RetryableError and return the result once it succeeds."""
        call_count = 0

        async def fail_twice_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("transient failure")
            return "ok"

        config = RetryConfig(max_attempts=4)
        executor = AsyncRetryExecutor(
            config=config,
            backoff=FixedBackoff(delay_ms=1),
        )

        result = await executor.execute(fail_twice_then_succeed)
        assert result == "ok"
        assert call_count == 3

    async def test_all_retries_exhausted_raises_retryable_error(self):
        """When all attempts fail with RetryableError, the last error is raised."""
        call_count = 0

        async def always_fail() -> str:
            nonlocal call_count
            call_count += 1
            raise RetryableError(f"attempt {call_count} failed")

        config = RetryConfig(max_attempts=3)
        executor = AsyncRetryExecutor(
            config=config,
            backoff=FixedBackoff(delay_ms=1),
        )

        with pytest.raises(RetryableError, match="attempt 3 failed"):
            await executor.execute(always_fail)
        assert call_count == 3


@pytest.mark.asyncio
class TestAsyncRetryExecutorNonRetryableError:
    async def test_non_retryable_error_raises_immediately(self):
        """NonRetryableError should not trigger any retries."""
        call_count = 0

        async def fail_permanently() -> str:
            nonlocal call_count
            call_count += 1
            raise NonRetryableError("bad request")

        executor = AsyncRetryExecutor(
            config=RetryConfig(max_attempts=5),
            backoff=FixedBackoff(delay_ms=1),
        )

        with pytest.raises(NonRetryableError, match="bad request"):
            await executor.execute(fail_permanently)
        assert call_count == 1  # no retries


@pytest.mark.asyncio
class TestAsyncRetryExecutorCircuitBreaker:
    async def test_circuit_breaker_open_error_passes_through(self):
        """CircuitBreakerOpenError should propagate without being retried."""
        cb = CircuitBreaker(
            "test_cb",
            CircuitBreakerConfig(failure_threshold=1, open_duration_ms=60_000),
        )
        # Force the circuit breaker into OPEN state
        cb.on_failure()

        executor = AsyncRetryExecutor(
            config=RetryConfig(max_attempts=3),
            circuit_breaker=cb,
            backoff=FixedBackoff(delay_ms=1),
        )

        call_count = 0

        async def should_not_run() -> str:
            nonlocal call_count
            call_count += 1
            return "unexpected"

        with pytest.raises(CircuitBreakerOpenError):
            await executor.execute(should_not_run)
        assert call_count == 0  # the coroutine was never called


@pytest.mark.asyncio
class TestAsyncRetryExecutorBackoff:
    async def test_backoff_delay_applied_between_retries(self):
        """Verify that asyncio.sleep is called between retries, producing measurable delay."""
        delay_ms = 80
        call_timestamps: list[float] = []

        async def record_and_fail() -> str:
            call_timestamps.append(time.monotonic())
            raise RetryableError("fail")

        config = RetryConfig(max_attempts=3)
        executor = AsyncRetryExecutor(
            config=config,
            backoff=FixedBackoff(delay_ms=delay_ms),
        )

        with pytest.raises(RetryableError):
            await executor.execute(record_and_fail)

        assert len(call_timestamps) == 3

        # There should be a gap of at least (delay_ms - tolerance) between consecutive calls
        tolerance_s = 0.03  # 30 ms tolerance for scheduling jitter
        expected_min_gap = (delay_ms / 1000.0) - tolerance_s

        gap_1 = call_timestamps[1] - call_timestamps[0]
        gap_2 = call_timestamps[2] - call_timestamps[1]

        assert gap_1 >= expected_min_gap, (
            f"Gap between attempt 0 and 1 was {gap_1:.4f}s, expected >= {expected_min_gap:.4f}s"
        )
        assert gap_2 >= expected_min_gap, (
            f"Gap between attempt 1 and 2 was {gap_2:.4f}s, expected >= {expected_min_gap:.4f}s"
        )


@pytest.mark.asyncio
class TestAsyncRetryExecutorHooks:
    async def test_on_retry_callback_fires(self):
        """on_retry should be called after each retryable failure (before the next attempt)."""
        events: list[tuple[int, str]] = []

        def on_retry(attempt: int, exc: Exception) -> None:
            events.append((attempt, str(exc)))

        call_count = 0

        async def fail_twice() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError(f"fail-{call_count}")
            return "done"

        executor = AsyncRetryExecutor(
            config=RetryConfig(max_attempts=4),
            backoff=FixedBackoff(delay_ms=1),
            on_retry=on_retry,
        )

        result = await executor.execute(fail_twice)
        assert result == "done"
        assert len(events) == 2
        assert events[0] == (0, "fail-1")
        assert events[1] == (1, "fail-2")

    async def test_on_failure_callback_fires_when_exhausted(self):
        """on_failure should be called when all attempts are exhausted."""
        failures: list[str] = []

        def on_failure(exc: Exception) -> None:
            failures.append(str(exc))

        async def always_fail() -> str:
            raise RetryableError("terminal")

        executor = AsyncRetryExecutor(
            config=RetryConfig(max_attempts=2),
            backoff=FixedBackoff(delay_ms=1),
            on_failure=on_failure,
        )

        with pytest.raises(RetryableError):
            await executor.execute(always_fail)

        assert len(failures) == 1
        assert failures[0] == "terminal"

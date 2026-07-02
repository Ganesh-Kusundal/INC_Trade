"""TDD tests for RetryExecutor — combines circuit breaker + rate limiter + retry."""

import pytest

from brokers.common.resilience.backoff import ExponentialBackoff
from brokers.common.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from brokers.common.resilience.errors import NonRetryableError, RetryableError
from brokers.common.resilience.rate_limiter import MultiBucketRateLimiter, RateLimitConfig
from brokers.common.resilience.retry import (
    RetryConfig,
    RetryExecutor,
)


class TestRetryConfig:
    def test_defaults(self):
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.max_retry_delay_ms == 30000

    def test_default_retryable_exceptions(self):
        """Default retryable_exceptions should include ConnectionError, TimeoutError, OSError."""
        config = RetryConfig()
        assert ConnectionError in config.retryable_exceptions
        assert TimeoutError in config.retryable_exceptions
        assert OSError in config.retryable_exceptions

    def test_custom_retryable_exceptions(self):
        """Should allow overriding retryable_exceptions."""
        config = RetryConfig(retryable_exceptions=(ValueError,))
        assert config.retryable_exceptions == (ValueError,)
        assert ConnectionError not in config.retryable_exceptions

    def test_validation_zero_attempts(self):
        with pytest.raises(ValueError):
            RetryConfig(max_attempts=0)


class TestRetryExecutorBasic:
    def test_successful_execution(self):
        executor = RetryExecutor()
        result = executor.execute(lambda: "success")
        assert result == "success"

    def test_retryable_error_retried(self):
        """Should retry on RetryableError up to max_attempts."""
        call_count = [0]

        def fail_twice():
            call_count[0] += 1
            if call_count[0] < 3:
                raise RetryableError("transient failure")
            return "ok"

        config = RetryConfig(max_attempts=4)
        executor = RetryExecutor(config)
        result = executor.execute(fail_twice)
        assert result == "ok"
        assert call_count[0] == 3

    def test_non_retryable_error_not_retried(self):
        """Should not retry on NonRetryableError."""
        call_count = [0]

        def fail():
            call_count[0] += 1
            raise NonRetryableError("bad request")

        executor = RetryExecutor()
        with pytest.raises(NonRetryableError):
            executor.execute(fail)
        assert call_count[0] == 1  # no retry

    def test_max_attempts_exceeded_raises(self):
        call_count = [0]

        def always_fail():
            call_count[0] += 1
            raise RetryableError("always fails")

        config = RetryConfig(max_attempts=3)
        executor = RetryExecutor(config)
        with pytest.raises(RetryableError):
            executor.execute(always_fail)
        assert call_count[0] == 3

    def test_default_exception_is_not_retryable(self):
        """Plain exceptions should NOT be retried by default."""
        call_count = [0]

        def fail():
            call_count[0] += 1
            raise ValueError("something went wrong")

        executor = RetryExecutor()
        with pytest.raises(ValueError):
            executor.execute(fail)
        assert call_count[0] == 1


class TestTransientExceptionRetries:
    """Tests for default transient exception retry behavior (A8 fix)."""

    def test_connection_error_is_retried(self):
        """ConnectionError should be retried by default."""
        call_count = [0]

        def fail_twice_then_succeed():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("connection refused")
            return "connected"

        config = RetryConfig(max_attempts=4)
        executor = RetryExecutor(
            config, backoff=ExponentialBackoff(base_delay_ms=10, max_delay_ms=50)
        )
        result = executor.execute(fail_twice_then_succeed)
        assert result == "connected"
        assert call_count[0] == 3

    def test_timeout_error_is_retried(self):
        """TimeoutError should be retried by default."""
        call_count = [0]

        def fail_once_then_succeed():
            call_count[0] += 1
            if call_count[0] < 2:
                raise TimeoutError("request timed out")
            return "timely"

        config = RetryConfig(max_attempts=3)
        executor = RetryExecutor(
            config, backoff=ExponentialBackoff(base_delay_ms=10, max_delay_ms=50)
        )
        result = executor.execute(fail_once_then_succeed)
        assert result == "timely"
        assert call_count[0] == 2

    def test_os_error_is_retried(self):
        """OSError should be retried by default."""
        call_count = [0]

        def fail_then_succeed():
            call_count[0] += 1
            if call_count[0] < 2:
                raise OSError("network unreachable")
            return "ok"

        config = RetryConfig(max_attempts=3)
        executor = RetryExecutor(
            config, backoff=ExponentialBackoff(base_delay_ms=10, max_delay_ms=50)
        )
        result = executor.execute(fail_then_succeed)
        assert result == "ok"
        assert call_count[0] == 2

    def test_value_error_still_not_retried(self):
        """ValueError should NOT be retried (backward compatibility)."""
        call_count = [0]

        def fail():
            call_count[0] += 1
            raise ValueError("invalid argument")

        executor = RetryExecutor()
        with pytest.raises(ValueError):
            executor.execute(fail)
        assert call_count[0] == 1

    def test_transient_exception_max_attempts_exceeded(self):
        """Transient exception that never succeeds should exhaust retries."""
        call_count = [0]

        def always_fail():
            call_count[0] += 1
            raise ConnectionError("permanent disconnect")

        config = RetryConfig(max_attempts=3)
        executor = RetryExecutor(
            config, backoff=ExponentialBackoff(base_delay_ms=10, max_delay_ms=50)
        )
        with pytest.raises(ConnectionError):
            executor.execute(always_fail)
        assert call_count[0] == 3

    def test_custom_exceptions_can_override_defaults(self):
        """Should allow custom retryable_exceptions to override defaults."""
        call_count = [0]

        def fail_with_custom():
            call_count[0] += 1
            if call_count[0] < 2:
                raise RuntimeError("custom transient")
            return "ok"

        config = RetryConfig(
            max_attempts=3,
            retryable_exceptions=(RuntimeError,),
        )
        executor = RetryExecutor(
            config, backoff=ExponentialBackoff(base_delay_ms=10, max_delay_ms=50)
        )
        result = executor.execute(fail_with_custom)
        assert result == "ok"
        assert call_count[0] == 2

    def test_default_exceptions_not_retried_when_overridden(self):
        """When retryable_exceptions is overridden, defaults should NOT be retried."""
        call_count = [0]

        def fail_with_connection_error():
            call_count[0] += 1
            raise ConnectionError("should not retry")

        config = RetryConfig(
            max_attempts=3,
            retryable_exceptions=(RuntimeError,),  # ConnectionError NOT in this tuple
        )
        executor = RetryExecutor(config)
        with pytest.raises(ConnectionError):
            executor.execute(fail_with_connection_error)
        assert call_count[0] == 1  # no retry


class TestRetryExecutorWithCircuitBreaker:
    def test_open_circuit_prevents_execution(self):
        cb = CircuitBreaker(
            "test", CircuitBreakerConfig(failure_threshold=2, open_duration_ms=5000)
        )
        executor = RetryExecutor(
            circuit_breaker=cb, backoff=ExponentialBackoff(base_delay_ms=10, max_delay_ms=100)
        )

        call_count = [0]

        def fails():
            call_count[0] += 1
            raise RetryableError("fail")

        # Trip the circuit breaker inside a single execute call
        # (first 2 retries fail, 3rd hits open circuit -> CircuitBreakerOpenError)
        with pytest.raises(Exception, match=".*"):
            executor.execute(fails)
        # The circuit opened during retries — next call should fast-fail
        with pytest.raises(Exception) as excinfo2:
            executor.execute(fails)
        assert "circuit" in str(excinfo2.value).lower() or "open" in str(excinfo2.value).lower()

    def test_circuit_breaker_success_resets(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2))
        executor = RetryExecutor(
            circuit_breaker=cb, backoff=ExponentialBackoff(base_delay_ms=10, max_delay_ms=100)
        )

        call_count = [0]

        def fail_once_then_succeed():
            call_count[0] += 1
            if call_count[0] == 1:
                raise RetryableError("transient")
            return "ok"

        result = executor.execute(fail_once_then_succeed)
        assert result == "ok"


class TestRetryExecutorWithRateLimiter:
    def test_rate_limiter_acquire_token(self):
        rate_limiter = MultiBucketRateLimiter(
            {
                "orders": RateLimitConfig(rate_per_second=100, capacity=5),
            }
        )
        executor = RetryExecutor(rate_limiter=rate_limiter, rate_limit_category="orders")

        # Should acquire a token before executing
        result = executor.execute(lambda: "done")
        assert result == "done"

    def test_rate_limiter_unknown_category_raises(self):
        rate_limiter = MultiBucketRateLimiter({"orders": RateLimitConfig()})
        executor = RetryExecutor(rate_limiter=rate_limiter, rate_limit_category="unknown")
        with pytest.raises(ValueError):
            executor.execute(lambda: "fail")


class TestRetryExecutorIntegration:
    def test_full_pipeline_success(self):
        """Rate limiter -> circuit breaker -> execution -> success."""
        rate_limiter = MultiBucketRateLimiter(
            {
                "api": RateLimitConfig(rate_per_second=100, capacity=10),
            }
        )
        cb = CircuitBreaker("api", CircuitBreakerConfig(failure_threshold=3))
        executor = RetryExecutor(
            config=RetryConfig(max_attempts=3),
            circuit_breaker=cb,
            rate_limiter=rate_limiter,
            rate_limit_category="api",
        )

        result = executor.execute(lambda: "hello")
        assert result == "hello"

    def test_event_hooks(self):
        """Should fire on_retry and on_failure callbacks."""
        events = []

        def on_retry(attempt, exc):
            events.append(("retry", attempt, str(exc)))

        def on_failure(final_exc):
            events.append(("failure", str(final_exc)))

        call_count = [0]

        def fails():
            call_count[0] += 1
            raise RetryableError("oops")

        config = RetryConfig(max_attempts=2)
        executor = RetryExecutor(config=config, on_retry=on_retry, on_failure=on_failure)

        with pytest.raises(RetryableError):
            executor.execute(fails)

        assert len(events) == 2  # one retry + one failure
        assert events[0][0] == "retry"
        assert events[1][0] == "failure"

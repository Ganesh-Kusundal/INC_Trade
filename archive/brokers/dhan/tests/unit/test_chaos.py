"""Chaos testing for Dhan broker adapter.

Simulates API downtime, network failures, and session expiry to verify
graceful degradation and recovery.

Extended for Task 6.2: Standardized Resilience Patterns
  - Circuit breaker trips under fault injection
  - Retry exhaustion scenarios
  - Rate limit enforcement
  - Graceful degradation paths
  - Recovery after circuit opens
  - Concurrent failures (thundering herd prevention)
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from brokers.common.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from brokers.common.resilience.errors import (
    CircuitBreakerOpenError,
    NonRetryableError,
    RetryableError,
)
from brokers.common.resilience.rate_limiter import (
    MultiBucketRateLimiter,
    RateLimitConfig,
)
from brokers.dhan.connection import DhanConnection
from brokers.dhan.gateway import BrokerGateway
from brokers.dhan.resilience.circuit_breaker import (
    DhanCircuitBreakerFactory,
    create_circuit_breakers,
)
from brokers.dhan.resilience.rate_limiter import (
    DhanRateLimiterFactory,
    DhanRateLimiterMetrics,
    create_rate_limiter,
)
from brokers.dhan.resilience.retry_executor import (
    ADMIN_POLICY,
    MARKET_DATA_POLICY,
    ORDERS_POLICY,
    PORTFOLIO_POLICY,
    create_retry_executor,
)

SAMPLE_ROWS = [
    {
        "SEM_TRADING_SYMBOL": "RELIANCE",
        "SEM_SMST_SECURITY_ID": "2885",
        "SEM_EXM_EXCH_ID": "NSE_EQ",
        "SEM_INSTRUMENT_NAME": "EQUITY",
        "SEM_LOT_UNITS": "1",
        "SEM_TICK_SIZE": "0.05",
        "SEM_CUSTOM_SYMBOL": "Reliance Industries",
    },
]


class FakeHttpClient:
    """Fake HTTP client for chaos testing."""

    def __init__(self):
        self.client_id = "test"
        self.access_token = "test"
        self._fail = False
        self._fail_count = 0
        self._success_count = 0
        self._rate_limit_count = 0

    def get(self, endpoint, **kw):
        if self._fail:
            self._fail_count += 1
            raise ConnectionError("Simulated network failure")
        if "/marketfeed" in endpoint:
            self._success_count += 1
            return {"data": {"NSE_EQ": {"2885": {"last_price": 2500}}}}
        self._success_count += 1
        return {"data": []}

    def post(self, endpoint, json=None):
        if self._fail:
            self._fail_count += 1
            raise ConnectionError("Simulated network failure")
        if "/marketfeed" in endpoint:
            self._success_count += 1
            return {"data": {"NSE_EQ": {"2885": {"last_price": 2500}}}}
        self._success_count += 1
        return {"data": []}

    def put(self, endpoint, json=None):
        if self._fail:
            self._fail_count += 1
            raise ConnectionError("Simulated network failure")
        self._success_count += 1
        return {"data": {}}

    def delete(self, endpoint):
        if self._fail:
            self._fail_count += 1
            raise ConnectionError("Simulated network failure")
        self._success_count += 1
        return {"data": {}}


@pytest.fixture()
def chaos_gateway() -> BrokerGateway:
    """Create a gateway with a fake HTTP client for chaos testing."""
    client = FakeHttpClient()
    conn = DhanConnection(client=client)
    conn.instruments.load_from_rows(SAMPLE_ROWS)
    gw = BrokerGateway(conn)
    gw._test_client = client
    return gw


# ============================================================================
# SECTION 1: Network Disconnect Tests (Legacy)
# ============================================================================


class TestNetworkDisconnect:
    """Simulate network failures."""

    def test_get_ltp_network_failure(self, chaos_gateway):
        chaos_gateway._test_client._fail = True
        with pytest.raises(ConnectionError):
            chaos_gateway.ltp("RELIANCE", "NSE")

    def test_get_quote_network_failure(self, chaos_gateway):
        chaos_gateway._test_client._fail = True
        with pytest.raises(ConnectionError):
            chaos_gateway.quote("RELIANCE", "NSE")

    def test_recovery_after_network_failure(self, chaos_gateway):
        chaos_gateway._test_client._fail = True
        with pytest.raises(ConnectionError):
            chaos_gateway.ltp("RELIANCE", "NSE")

        chaos_gateway._test_client._fail = False
        result = chaos_gateway.ltp("RELIANCE", "NSE")
        assert result is not None


# ============================================================================
# SECTION 2: Circuit Breaker Tests (Extended)
# ============================================================================


class TestCircuitBreakerBasic:
    """Verify basic circuit breaker functionality."""

    def test_circuit_opens_after_failures(self, chaos_gateway):
        config = CircuitBreakerConfig(failure_threshold=3, open_duration_ms=1000)
        cb = CircuitBreaker("test", config)

        for _ in range(3):
            cb.on_failure()

        assert cb.state == CircuitState.OPEN

    def test_circuit_half_open_after_timeout(self):
        config = CircuitBreakerConfig(failure_threshold=2, open_duration_ms=100)
        cb = CircuitBreaker("test", config)

        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_circuit_closes_after_successes_in_half_open(self):
        config = CircuitBreakerConfig(
            failure_threshold=2, success_threshold=2, open_duration_ms=100
        )
        cb = CircuitBreaker("test", config)

        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        cb.on_success()
        cb.on_success()
        assert cb.state == CircuitState.CLOSED

    def test_circuit_reopens_on_failure_in_half_open(self):
        config = CircuitBreakerConfig(failure_threshold=2, open_duration_ms=100)
        cb = CircuitBreaker("test", config)

        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.15)
        assert cb.state == CircuitState.HALF_OPEN

        cb.on_failure()
        assert cb.state == CircuitState.OPEN

    def test_circuit_reset(self):
        config = CircuitBreakerConfig(failure_threshold=2, open_duration_ms=10000)
        cb = CircuitBreaker("test", config)

        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.metrics.failure_count == 0


class TestDhanCircuitBreakerFactory:
    """Test Dhan-specific circuit breaker factory."""

    def test_create_orders(self):
        cb = DhanCircuitBreakerFactory.create_orders()
        assert cb.name == "dhan-orders"
        assert cb.config.failure_threshold == 3
        assert cb.config.open_duration_ms == 30_000
        assert cb.config.success_threshold == 3

    def test_create_market_data(self):
        cb = DhanCircuitBreakerFactory.create_market_data()
        assert cb.name == "dhan-market-data"
        assert cb.config.failure_threshold == 5
        assert cb.config.open_duration_ms == 30_000

    def test_create_portfolio(self):
        cb = DhanCircuitBreakerFactory.create_portfolio()
        assert cb.name == "dhan-portfolio"
        assert cb.config.failure_threshold == 5

    def test_create_admin(self):
        cb = DhanCircuitBreakerFactory.create_admin()
        assert cb.name == "dhan-admin"
        assert cb.config.failure_threshold == 5

    def test_create_all_circuit_breakers(self):
        cbs = create_circuit_breakers()
        assert len(cbs) == 4
        assert set(cbs.keys()) == {"orders", "market_data", "portfolio", "admin"}

    def test_orders_more_sensitive_than_market_data(self):
        """Orders should have lower failure threshold (more sensitive)."""
        cbs = create_circuit_breakers()
        assert cbs["orders"].config.failure_threshold < cbs["market_data"].config.failure_threshold

    def test_circuit_breaker_state_observable(self):
        """Circuit breaker state must be observable for health checks."""
        cb = DhanCircuitBreakerFactory.create_orders()
        assert hasattr(cb, "state")
        assert hasattr(cb, "metrics")
        assert cb.state == CircuitState.CLOSED

    def test_circuit_breaker_metrics_snapshot(self):
        cb = DhanCircuitBreakerFactory.create_market_data()
        cb.on_success()
        cb.on_success()
        cb.on_failure()

        metrics = cb.metrics
        assert metrics.success_count == 2
        assert metrics.failure_count == 1
        assert metrics.total_calls == 3


class TestCircuitBreakerThreadSafety:
    """Verify circuit breaker is thread-safe."""

    def test_concurrent_failures(self):
        """Multiple threads triggering failures should not corrupt state."""
        config = CircuitBreakerConfig(failure_threshold=10, open_duration_ms=10000)
        cb = CircuitBreaker("test", config)

        def trigger_failures():
            for _ in range(5):
                cb.on_failure()

        threads = [threading.Thread(target=trigger_failures) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have opened after 10 failures
        assert cb.state == CircuitState.OPEN

    def test_concurrent_state_reads(self):
        """Multiple threads reading state should not block or corrupt."""
        config = CircuitBreakerConfig(failure_threshold=100, open_duration_ms=100)
        cb = CircuitBreaker("test", config)
        states = []

        def read_state():
            for _ in range(10):
                states.append(cb.state)
                time.sleep(0.01)

        threads = [threading.Thread(target=read_state) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(states) == 50
        assert all(s == CircuitState.CLOSED for s in states)


# ============================================================================
# SECTION 3: Retry Executor Tests
# ============================================================================


class TestDhanRetryPolicies:
    """Test Dhan-specific retry policies."""

    def test_orders_policy(self):
        assert ORDERS_POLICY.category == "orders"
        assert ORDERS_POLICY.max_attempts == 3
        assert ORDERS_POLICY.base_delay_ms == 1000.0
        assert ORDERS_POLICY.max_delay_ms == 8000.0

    def test_market_data_policy(self):
        assert MARKET_DATA_POLICY.category == "market_data"
        assert MARKET_DATA_POLICY.max_attempts == 2
        assert MARKET_DATA_POLICY.base_delay_ms == 500.0
        assert MARKET_DATA_POLICY.max_delay_ms == 4000.0

    def test_portfolio_policy(self):
        assert PORTFOLIO_POLICY.category == "portfolio"
        assert PORTFOLIO_POLICY.max_attempts == 3

    def test_admin_policy(self):
        assert ADMIN_POLICY.category == "admin"
        assert ADMIN_POLICY.max_attempts == 3

    def test_retry_config_conversion(self):
        config = ORDERS_POLICY.to_retry_config()
        assert config.max_attempts == 3
        assert config.max_retry_delay_ms == 8000

    def test_backoff_creation(self):
        backoff = ORDERS_POLICY.to_backoff()
        delay_0 = backoff.delay(0)
        delay_1 = backoff.delay(1)
        assert delay_1 > delay_0  # Exponential increase


class TestDhanRetryExecutor:
    """Test Dhan retry executor integration."""

    def test_create_orders_executor(self):
        cb = DhanCircuitBreakerFactory.create_orders()
        executor = create_retry_executor("orders", circuit_breaker=cb)
        assert executor.config.max_attempts == 3

    def test_create_market_data_executor(self):
        cb = DhanCircuitBreakerFactory.create_market_data()
        executor = create_retry_executor("market_data", circuit_breaker=cb)
        assert executor.config.max_attempts == 2

    def test_create_with_rate_limiter(self):
        rl = create_rate_limiter()
        cb = DhanCircuitBreakerFactory.create_orders()
        executor = create_retry_executor("orders", circuit_breaker=cb, rate_limiter=rl)
        assert executor.rate_limiter is not None

    def test_retry_exhaustion_raises_error(self):
        """When all retries are exhausted, the last error should be raised."""
        cb = DhanCircuitBreakerFactory.create_orders()
        executor = create_retry_executor("orders", circuit_breaker=cb)

        call_count = [0]

        def always_fail():
            call_count[0] += 1
            raise RetryableError("transient failure")

        with pytest.raises(RetryableError, match="transient failure"):
            executor.execute(always_fail)

        assert call_count[0] == 3

    def test_retry_with_eventual_success(self):
        """Should succeed after transient failures."""
        cb = DhanCircuitBreakerFactory.create_market_data()
        executor = create_retry_executor("market_data", circuit_breaker=cb)

        call_count = [0]

        def fail_once_then_succeed():
            call_count[0] += 1
            if call_count[0] < 2:
                raise RetryableError("transient")
            return "success"

        result = executor.execute(fail_once_then_succeed)
        assert result == "success"
        assert call_count[0] == 2

    def test_non_retryable_error_fails_immediately(self):
        """Non-retryable errors should not trigger retries."""
        cb = DhanCircuitBreakerFactory.create_orders()
        executor = create_retry_executor("orders", circuit_breaker=cb)

        call_count = [0]

        def fail_with_non_retryable():
            call_count[0] += 1
            raise NonRetryableError("permanent failure")

        with pytest.raises(NonRetryableError):
            executor.execute(fail_with_non_retryable)

        assert call_count[0] == 1  # Only called once

    def test_circuit_breaker_prevents_execution_when_open(self):
        """Open circuit breaker should prevent execution."""
        cb = DhanCircuitBreakerFactory.create_orders()
        executor = create_retry_executor("orders", circuit_breaker=cb)

        # Trip the circuit breaker
        for _ in range(3):
            cb.on_failure()

        assert cb.state == CircuitState.OPEN

        def should_not_run():
            return "unexpected"

        with pytest.raises(CircuitBreakerOpenError):
            executor.execute(should_not_run)


# ============================================================================
# SECTION 4: Rate Limiter Tests
# ============================================================================


class TestDhanRateLimiterFactory:
    """Test Dhan rate limiter factory."""

    def test_create_rate_limiter(self):
        rl = create_rate_limiter()
        assert isinstance(rl, MultiBucketRateLimiter)
        assert set(rl.categories()) == {"orders", "market_data", "portfolio", "admin"}

    def test_orders_rate_limit(self):
        config = DhanRateLimiterFactory.create_config("orders")
        assert config.rate_per_second == 25.0
        assert config.capacity == 25

    def test_market_data_rate_limit(self):
        config = DhanRateLimiterFactory.create_config("market_data")
        assert config.rate_per_second == 10.0
        assert config.capacity == 10

    def test_portfolio_rate_limit(self):
        config = DhanRateLimiterFactory.create_config("portfolio")
        assert config.rate_per_second == 20.0
        assert config.capacity == 20

    def test_admin_rate_limit(self):
        config = DhanRateLimiterFactory.create_config("admin")
        assert config.rate_per_second == 10.0
        assert config.capacity == 10

    def test_unknown_category_defaults_to_admin(self):
        config = DhanRateLimiterFactory.create_config("unknown")
        admin_config = DhanRateLimiterFactory.create_config("admin")
        assert config.rate_per_second == admin_config.rate_per_second


class TestRateLimiterEnforcement:
    """Verify rate limiter enforces limits."""

    def test_acquire_within_limit(self):
        """Requests within rate limit should succeed immediately."""
        rl = create_rate_limiter()
        assert rl.acquire("orders", tokens=1, timeout=1.0) is True

    def test_acquire_exceeds_capacity(self):
        """Requests exceeding capacity should timeout."""
        config = RateLimitConfig(rate_per_second=10.0, capacity=2)
        rl = MultiBucketRateLimiter({"test": config})

        # Consume all tokens
        assert rl.acquire("test", tokens=1, timeout=0.1) is True
        assert rl.acquire("test", tokens=1, timeout=0.1) is True

        # Third request should timeout
        assert rl.acquire("test", tokens=1, timeout=0.01) is False

    def test_token_refill(self):
        """Tokens should refill over time."""
        config = RateLimitConfig(rate_per_second=100.0, capacity=2)
        rl = MultiBucketRateLimiter({"test": config})

        # Consume all tokens
        rl.acquire("test", tokens=1, timeout=0.1)
        rl.acquire("test", tokens=1, timeout=0.1)

        # Wait for refill
        time.sleep(0.05)

        # Should have tokens now
        assert rl.acquire("test", tokens=1, timeout=0.1) is True


class TestRateLimiterMetrics:
    """Test rate limiter metrics collection."""

    def test_record_request(self):
        metrics = DhanRateLimiterMetrics()
        metrics.record_request("orders")
        assert metrics.get_requests_per_second("orders") >= 0.0

    def test_record_rejection(self):
        metrics = DhanRateLimiterMetrics()
        metrics.record_rejection("orders")
        assert metrics.get_rejections("orders") == 1

    def test_queue_depth_tracking(self):
        metrics = DhanRateLimiterMetrics()
        metrics.increment_queue_depth("orders")
        metrics.increment_queue_depth("orders")
        assert metrics.get_queue_depth("orders") == 2

        metrics.decrement_queue_depth("orders")
        assert metrics.get_queue_depth("orders") == 1

    def test_snapshot(self):
        metrics = DhanRateLimiterMetrics()
        metrics.record_request("orders")
        metrics.record_rejection("market_data")
        # Need to also record a request for market_data to appear in snapshot
        metrics.record_request("market_data")

        snapshot = metrics.snapshot()
        assert "orders" in snapshot
        assert "market_data" in snapshot
        assert snapshot["market_data"]["rejections"] == 1


# ============================================================================
# SECTION 5: Graceful Degradation Tests
# ============================================================================


class TestGracefulDegradation:
    """Verify graceful degradation paths."""

    def test_rate_limiter_fallback_when_not_configured(self):
        """Requests should succeed when no rate limiter is configured."""
        from brokers.dhan.http_client import DhanHttpClient

        client = DhanHttpClient(client_id="test", access_token="test")
        assert client._acquire_rate_limit_token("/orders") is True

    def test_circuit_breaker_fallback_to_legacy(self):
        """HTTP client should fall back to legacy circuit breaker if specific one not provided."""
        from brokers.dhan.http_client import DhanHttpClient

        legacy_cb = CircuitBreaker("legacy", CircuitBreakerConfig(failure_threshold=5))
        client = DhanHttpClient(
            client_id="test",
            access_token="test",
            circuit_breaker=legacy_cb,
        )

        cb = client._get_circuit_breaker("/orders")
        assert cb is legacy_cb

    def test_unknown_category_defaults_to_admin(self):
        """Unknown endpoint categories should use admin policy."""
        executor = create_retry_executor("unknown_category")
        assert executor.config.max_attempts == ADMIN_POLICY.max_attempts


# ============================================================================
# SECTION 6: Recovery Tests
# ============================================================================


class TestRecoveryScenarios:
    """Test recovery after circuit opens."""

    def test_recovery_after_circuit_opens(self):
        """Circuit should transition to half-open after timeout."""
        # Use a short timeout for testing
        config = CircuitBreakerConfig(failure_threshold=3, open_duration_ms=50)
        cb = CircuitBreaker("test-recovery", config)

        # Trip the circuit
        for _ in range(3):
            cb.on_failure()

        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.1)

        # Should transition to half-open
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True

    def test_successful_recovery_closes_circuit(self):
        """Successful requests in half-open should close the circuit."""
        config = CircuitBreakerConfig(
            failure_threshold=2, success_threshold=2, open_duration_ms=50
        )
        cb = CircuitBreaker("test", config)

        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

        cb.on_success()
        cb.on_success()
        assert cb.state == CircuitState.CLOSED

    def test_failed_recovery_reopens_circuit(self):
        """Failed request in half-open should immediately re-open."""
        config = CircuitBreakerConfig(failure_threshold=2, open_duration_ms=50)
        cb = CircuitBreaker("test", config)

        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

        cb.on_failure()
        assert cb.state == CircuitState.OPEN


# ============================================================================
# SECTION 7: Concurrent Failures (Thundering Herd Prevention)
# ============================================================================


class TestConcurrentFailures:
    """Test behavior under concurrent failures."""

    def test_concurrent_requests_with_open_circuit(self):
        """All concurrent requests should fail fast when circuit is open."""
        cb = DhanCircuitBreakerFactory.create_orders()
        executor = create_retry_executor("orders", circuit_breaker=cb)

        # Trip the circuit
        for _ in range(3):
            cb.on_failure()

        assert cb.state == CircuitState.OPEN

        errors = []

        def make_request():
            try:
                executor.execute(lambda: "should not run")
            except CircuitBreakerOpenError:
                errors.append("circuit_open")

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(make_request) for _ in range(10)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 10

    def test_thundering_herd_prevention(self):
        """Circuit breaker should prevent thundering herd after failure."""
        config = CircuitBreakerConfig(failure_threshold=5, open_duration_ms=100)
        cb = CircuitBreaker("test", config)

        # Simulate failures from multiple threads
        def trigger_failure():
            cb.on_failure()

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(trigger_failure) for _ in range(10)]
            for f in as_completed(futures):
                f.result()

        # Circuit should be open
        assert cb.state == CircuitState.OPEN

        # No more requests should be allowed
        assert cb.allow_request() is False

    def test_concurrent_rate_limit_acquisition(self):
        """Rate limiter should handle concurrent acquisitions correctly."""
        config = RateLimitConfig(rate_per_second=10.0, capacity=10)
        rl = MultiBucketRateLimiter({"test": config})

        successes = []
        failures = []

        def acquire_token():
            if rl.acquire("test", tokens=1, timeout=0.01):
                successes.append(True)
            else:
                failures.append(True)

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(acquire_token) for _ in range(20)]
            for f in as_completed(futures):
                f.result()

        # Some should succeed (up to capacity), some should fail
        assert len(successes) >= 1
        assert len(failures) >= 1
        assert len(successes) + len(failures) == 20


# ============================================================================
# SECTION 8: Fault Injection Tests
# ============================================================================


class TestFaultInjection:
    """Test resilience under injected faults."""

    def test_circuit_breaker_trips_under_fault_injection(self):
        """Circuit breaker should trip after configured failures."""
        cb = DhanCircuitBreakerFactory.create_market_data()

        for _ in range(5):
            cb.on_failure()

        assert cb.state == CircuitState.OPEN

    def test_retry_exhaustion_under_persistent_fault(self):
        """Retry executor should exhaust retries under persistent faults."""
        cb = DhanCircuitBreakerFactory.create_portfolio()
        executor = create_retry_executor("portfolio", circuit_breaker=cb)

        call_count = [0]

        def persistent_fault():
            call_count[0] += 1
            raise RetryableError("persistent fault")

        with pytest.raises(RetryableError):
            executor.execute(persistent_fault)

        assert call_count[0] == 3

    def test_rate_limit_enforcement_under_burst(self):
        """Rate limiter should enforce limits under burst traffic."""
        config = RateLimitConfig(rate_per_second=10.0, capacity=3)
        rl = MultiBucketRateLimiter({"test": config})

        # Burst of 5 requests
        results = []
        for _ in range(5):
            results.append(rl.acquire("test", tokens=1, timeout=0.01))

        # First 3 should succeed, last 2 should timeout
        assert results[:3] == [True, True, True]
        assert results[3:] == [False, False]

    def test_mixed_fault_types(self):
        """System should handle mix of retryable and non-retryable faults."""
        cb = DhanCircuitBreakerFactory.create_orders()
        executor = create_retry_executor("orders", circuit_breaker=cb)

        # Non-retryable should fail immediately
        with pytest.raises(NonRetryableError):
            executor.execute(lambda: (_ for _ in ()).throw(NonRetryableError("permanent")))


# ============================================================================
# SECTION 9: Integration Tests
# ============================================================================


class TestResilienceIntegration:
    """Test resilience patterns working together."""

    def test_circuit_breaker_and_retry_executor_together(self):
        """Circuit breaker and retry executor should work together."""
        cb = DhanCircuitBreakerFactory.create_admin()
        rl = create_rate_limiter()
        executor = create_retry_executor("admin", circuit_breaker=cb, rate_limiter=rl)

        call_count = [0]

        def fail_then_succeed():
            call_count[0] += 1
            if call_count[0] < 2:
                raise RetryableError("transient")
            return "success"

        result = executor.execute(fail_then_succeed)
        assert result == "success"
        assert call_count[0] == 2

    def test_rate_limiter_does_not_block_circuit_breaker(self):
        """Rate limiter should not interfere with circuit breaker logic."""
        cb = DhanCircuitBreakerFactory.create_market_data()
        rl = create_rate_limiter()
        executor = create_retry_executor("market_data", circuit_breaker=cb, rate_limiter=rl)

        # Trip circuit breaker
        for _ in range(5):
            cb.on_failure()

        # Should fail with circuit open, not rate limit
        with pytest.raises(CircuitBreakerOpenError):
            executor.execute(lambda: "should not run")

    def test_all_circuit_breakers_independent(self):
        """Failure in one category should not affect others."""
        cbs = create_circuit_breakers()

        # Trip orders circuit breaker
        for _ in range(3):
            cbs["orders"].on_failure()

        assert cbs["orders"].state == CircuitState.OPEN
        assert cbs["market_data"].state == CircuitState.CLOSED
        assert cbs["portfolio"].state == CircuitState.CLOSED
        assert cbs["admin"].state == CircuitState.CLOSED


# ============================================================================
# SECTION 10: Rate Limiting Legacy Tests (Preserved)
# ============================================================================


class TestRateLimiting:
    """Verify rate limiting prevents rapid requests."""

    def test_rate_limit_exists(self):
        from brokers.dhan.http_client import _RATE_LIMITS

        assert "/marketfeed/quote" in _RATE_LIMITS
        assert "/optionchain" in _RATE_LIMITS
        assert _RATE_LIMITS["/marketfeed/quote"] > 0
        assert _RATE_LIMITS["/optionchain"] > 0

"""TDD tests for CircuitBreaker — failure threshold-based circuit breaker."""

import time

import pytest

from brokers.common.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)


class TestCircuitBreakerInitialization:
    def test_default_config(self):
        cb = CircuitBreaker("test")
        assert cb.name == "test"
        assert cb.state == CircuitState.CLOSED
        assert cb.config.failure_threshold == 5
        assert cb.config.success_threshold == 3
        assert cb.config.open_duration_ms == 30000

    def test_custom_config(self):
        config = CircuitBreakerConfig(
            failure_threshold=3, success_threshold=2, open_duration_ms=5000
        )
        cb = CircuitBreaker("custom", config)
        assert cb.config.failure_threshold == 3
        assert cb.config.success_threshold == 2
        assert cb.config.open_duration_ms == 5000

    def test_config_validation(self):
        with pytest.raises(ValueError):
            CircuitBreakerConfig(failure_threshold=0)
        with pytest.raises(ValueError):
            CircuitBreakerConfig(success_threshold=0)
        with pytest.raises(ValueError):
            CircuitBreakerConfig(open_duration_ms=0)


class TestCircuitBreakerStateTransitions:
    def test_closed_starts_closed(self):
        cb = CircuitBreaker("test")
        assert cb.allow_request() is True

    def test_failure_threshold_opens_circuit(self):
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test", config)
        for _ in range(3):
            cb.on_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_success_resets_failure_count(self):
        config = CircuitBreakerConfig(failure_threshold=3)
        cb = CircuitBreaker("test", config)
        cb.on_failure()
        cb.on_failure()
        cb.on_success()  # reset
        cb.on_failure()
        assert cb.state == CircuitState.CLOSED  # only 1 failure after reset

    def test_half_open_after_timeout(self):
        config = CircuitBreakerConfig(failure_threshold=2, open_duration_ms=100)
        cb = CircuitBreaker("test", config)
        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

        time.sleep(0.15)  # wait for open duration
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True

    def test_success_in_half_open_closes_circuit(self):
        config = CircuitBreakerConfig(failure_threshold=2, success_threshold=2, open_duration_ms=50)
        cb = CircuitBreaker("test", config)
        # Open the circuit
        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

        # One success should not close yet
        cb.on_success()
        assert cb.state == CircuitState.HALF_OPEN
        # Second success reaches threshold -> close
        cb.on_success()
        assert cb.state == CircuitState.CLOSED

    def test_failure_in_half_open_reopens(self):
        config = CircuitBreakerConfig(failure_threshold=2, open_duration_ms=50)
        cb = CircuitBreaker("test", config)
        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        time.sleep(0.1)
        assert cb.state == CircuitState.HALF_OPEN

        # Failure in half-open sends back to open
        cb.on_failure()
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerMetrics:
    def test_metrics_track_counts(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=3))
        cb.on_failure()
        cb.on_failure()
        assert cb.metrics.failure_count == 2
        cb.on_success()
        assert cb.metrics.success_count == 1
        # Success in CLOSED resets failure count
        assert cb.metrics.failure_count == 0

    def test_metrics_track_state_changes(self):
        cb = CircuitBreaker("test", CircuitBreakerConfig(failure_threshold=2))
        assert cb.metrics.state_change_count == 0
        cb.on_failure()
        cb.on_failure()
        assert cb.metrics.state_change_count >= 1


class TestCircuitBreakerReset:
    def test_reset(self):
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker("test", config)
        cb.on_failure()
        cb.on_failure()
        assert cb.state == CircuitState.OPEN

        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.metrics.failure_count == 0
        assert cb.metrics.success_count == 0
        assert cb.allow_request() is True


class TestCircuitBreakerString:
    def test_string_representation(self):
        cb = CircuitBreaker("my-broker")
        s = str(cb)
        assert "my-broker" in s
        assert "CLOSED" in s

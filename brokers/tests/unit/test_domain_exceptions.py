"""Tests for domain exceptions."""

from __future__ import annotations

from brokers.domain.exceptions import (
    AuthenticationError,
    BrokerDegradedError,
    BrokerError,
    BrokerServerError,
    CircuitOpenError,
    ConfigError,
    DataError,
    InstrumentNotFoundError,
    NetworkError,
    NonRetryableError,
    NotSupportedError,
    OrderRejectedError,
    RateLimitError,
    RetryableError,
    TradeXV2Error,
    ValidationError,
)


class TestTradeXV2Error:
    def test_root_exception(self):
        err = TradeXV2Error("root error")
        assert str(err) == "root error"
        assert isinstance(err, Exception)


class TestConfigError:
    def test_inherits_from_root(self):
        err = ConfigError("missing key")
        assert isinstance(err, TradeXV2Error)


class TestDataError:
    def test_inherits_from_root(self):
        err = DataError("bad data")
        assert isinstance(err, TradeXV2Error)


class TestValidationError:
    def test_inherits_from_root(self):
        err = ValidationError("invalid input")
        assert isinstance(err, TradeXV2Error)


class TestBrokerError:
    def test_base_error(self):
        err = BrokerError("something broke")
        assert str(err) == "something broke"
        assert isinstance(err, TradeXV2Error)

    def test_with_code(self):
        err = BrokerError("bad request", code="INVALID_INPUT")
        assert err.code == "INVALID_INPUT"


class TestRetryableError:
    def test_inherits_from_broker_error(self):
        err = RetryableError("transient")
        assert isinstance(err, BrokerError)


class TestNonRetryableError:
    def test_inherits_from_broker_error(self):
        err = NonRetryableError("permanent")
        assert isinstance(err, BrokerError)


class TestNetworkError:
    def test_inherits_from_retryable(self):
        err = NetworkError("connection reset")
        assert isinstance(err, RetryableError)
        assert isinstance(err, BrokerError)


class TestBrokerServerError:
    def test_inherits_from_broker_error(self):
        err = BrokerServerError("500 Internal Server Error")
        assert isinstance(err, BrokerError)


class TestOrderRejectedError:
    def test_create(self):
        err = OrderRejectedError("Insufficient margin")
        assert "Insufficient margin" in str(err)
        assert isinstance(err, BrokerError)

    def test_with_order_id(self):
        err = OrderRejectedError("Margin shortfall", order_id="ORD001")
        assert err.order_id == "ORD001"


class TestRateLimitError:
    def test_create(self):
        err = RateLimitError("Too many requests")
        assert isinstance(err, BrokerError)
        assert err.retry_after is None

    def test_with_retry_after(self):
        err = RateLimitError("Slow down", retry_after=30.0)
        assert err.retry_after == 30.0


class TestCircuitOpenError:
    def test_create(self):
        err = CircuitOpenError("Circuit open for /orders")
        assert isinstance(err, BrokerError)
        assert err.code == "CIRCUIT_OPEN"


class TestAuthenticationError:
    def test_create(self):
        err = AuthenticationError("Token expired")
        assert isinstance(err, BrokerError)
        assert err.code == "AUTH_ERROR"


class TestInstrumentNotFoundError:
    def test_create(self):
        err = InstrumentNotFoundError("RELIANCE2024")
        assert "RELIANCE2024" in str(err)
        assert isinstance(err, BrokerError)


class TestNotSupportedError:
    def test_create(self):
        err = NotSupportedError()
        assert isinstance(err, BrokerError)
        assert err.code == "NOT_SUPPORTED"


class TestBrokerDegradedError:
    def test_create(self):
        err = BrokerDegradedError("High latency")
        assert isinstance(err, BrokerError)
        assert err.code == "BROKER_DEGRADED"

    def test_with_health_status(self):
        status = {"latency_ms": 5000, "error_rate": 0.5}
        err = BrokerDegradedError("Degraded", health_status=status)
        assert err.health_status == status

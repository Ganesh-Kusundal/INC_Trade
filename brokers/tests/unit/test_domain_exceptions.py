"""Tests for domain exceptions."""

from __future__ import annotations


from brokers.domain.exceptions import (
    AuthenticationError,
    BrokerError,
    CircuitOpenError,
    InstrumentNotFoundError,
    OrderRejectedError,
    RateLimitError,
)


class TestBrokerError:
    def test_base_error(self):
        err = BrokerError("something broke")
        assert str(err) == "something broke"
        assert isinstance(err, Exception)

    def test_with_code(self):
        err = BrokerError("bad request", code="INVALID_INPUT")
        assert err.code == "INVALID_INPUT"


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


class TestAuthenticationError:
    def test_create(self):
        err = AuthenticationError("Token expired")
        assert isinstance(err, BrokerError)


class TestInstrumentNotFoundError:
    def test_create(self):
        err = InstrumentNotFoundError("RELIANCE2024")
        assert "RELIANCE2024" in str(err)
        assert isinstance(err, BrokerError)

"""Tests for infrastructure.global_exception_handler — import resolution + HTTP mapping."""

from __future__ import annotations


class TestImportResolution:
    """Fix #1: broken imports must not crash the API server."""

    def test_import_succeeds(self):
        """The module must import without ImportError."""
        from infrastructure.global_exception_handler import setup_exception_handlers
        assert callable(setup_exception_handlers)

    def test_all_exception_classes_importable(self):
        """All mapped exception classes must be importable."""
        from brokers.common.resilience.errors import (
            AuthenticationError,
            BrokerError,
            NetworkError,
            NonRetryableError,
            OrderError,
            RateLimitError,
            RetryableError,
            TradeXV2Error,
        )
        # Verify hierarchy
        assert issubclass(AuthenticationError, BrokerError)
        assert issubclass(RateLimitError, BrokerError)
        assert issubclass(OrderError, BrokerError)
        assert issubclass(RetryableError, BrokerError)
        assert issubclass(NonRetryableError, BrokerError)
        assert issubclass(BrokerError, TradeXV2Error)
        assert issubclass(NetworkError, RetryableError)


class TestExceptionMapping:
    """Each mapped exception must produce the correct HTTP status code."""

    def _map(self, exc):
        from infrastructure.global_exception_handler import _map_exception_to_response
        return _map_exception_to_response(exc)

    def test_authentication_error_returns_401(self):
        from brokers.common.resilience.errors import AuthenticationError
        resp = self._map(AuthenticationError("bad creds"))
        assert resp.status_code == 401

    def test_rate_limit_error_returns_429(self):
        from brokers.common.resilience.errors import RateLimitError
        resp = self._map(RateLimitError("slow down"))
        assert resp.status_code == 429

    def test_order_error_returns_400(self):
        from brokers.common.resilience.errors import OrderError
        resp = self._map(OrderError("invalid qty"))
        assert resp.status_code == 400

    def test_retryable_error_returns_503(self):
        from brokers.common.resilience.errors import RetryableError
        resp = self._map(RetryableError("timeout"))
        assert resp.status_code == 503

    def test_non_retryable_error_returns_500(self):
        from brokers.common.resilience.errors import NonRetryableError
        resp = self._map(NonRetryableError("permanent"))
        assert resp.status_code == 500

    def test_generic_broker_error_returns_502(self):
        from brokers.common.resilience.errors import BrokerError
        resp = self._map(BrokerError("unknown"))
        assert resp.status_code == 502

    def test_base_tradexv2_error_returns_500(self):
        from brokers.common.resilience.errors import TradeXV2Error
        resp = self._map(TradeXV2Error("base"))
        assert resp.status_code == 500

    # --- Previously unmapped exception types (T8 coverage gap) ---

    def test_circuit_breaker_open_returns_503(self):
        from brokers.common.resilience.errors import CircuitBreakerOpenError
        resp = self._map(CircuitBreakerOpenError("test-breaker"))
        assert resp.status_code == 503

    def test_broker_degraded_returns_503(self):
        from brokers.common.resilience.errors import BrokerDegradedError
        resp = self._map(BrokerDegradedError())
        assert resp.status_code == 503

    def test_instrument_not_found_returns_404(self):
        from brokers.common.resilience.errors import InstrumentNotFoundError
        resp = self._map(InstrumentNotFoundError("missing"))
        assert resp.status_code == 404

    def test_validation_error_returns_422(self):
        from brokers.common.resilience.errors import ValidationError
        resp = self._map(ValidationError("bad input"))
        assert resp.status_code == 422

    def test_not_supported_returns_501(self):
        from brokers.common.resilience.errors import NotSupportedError
        resp = self._map(NotSupportedError("nope"))
        assert resp.status_code == 501

    def test_exit_all_returns_501(self):
        """ExitAllError inherits NotSupportedError -> 501."""
        from brokers.common.resilience.errors import ExitAllError
        resp = self._map(ExitAllError("kill switch failed"))
        assert resp.status_code == 501

    def test_config_error_returns_500(self):
        from brokers.common.resilience.errors import ConfigError
        resp = self._map(ConfigError("missing key"))
        assert resp.status_code == 500

    def test_data_error_returns_500(self):
        from brokers.common.resilience.errors import DataError
        resp = self._map(DataError("corrupt"))
        assert resp.status_code == 500

    def test_network_error_returns_503(self):
        """NetworkError inherits RetryableError -> 503."""
        from brokers.common.resilience.errors import NetworkError
        resp = self._map(NetworkError("connection refused"))
        assert resp.status_code == 503

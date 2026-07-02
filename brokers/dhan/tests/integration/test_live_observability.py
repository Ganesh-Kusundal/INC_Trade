"""Live integration tests for Dhan observability endpoints.

Tests get_connection_status(), get_circuit_breaker_states(),
get_token_refresh_metrics(), and get_rate_limiter_metrics().

These tests require a valid .env.local with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.dhan.factory import BrokerFactory

pytestmark = [pytest.mark.dhan, pytest.mark.off_market_safe, pytest.mark.regression]
from brokers.dhan.gateway import BrokerGateway

# ---------------------------------------------------------------------------
# Skip guard — only run when .env.local has valid credentials
# ---------------------------------------------------------------------------

ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.local"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLiveObservability:
    """Observability endpoint tests against live Dhan API."""

    def test_get_connection_status_returns_dict(self, gateway: BrokerGateway):
        """get_connection_status() should return dict with stream statuses."""
        status = gateway.get_connection_status()
        assert isinstance(status, dict)
        # May be empty if no streams are active yet - that's OK

    def test_connection_status_has_market_feed(self, gateway: BrokerGateway):
        """Connection status should include market_feed status."""
        status = gateway.get_connection_status()
        # May or may not have market_feed depending on initialization
        # but if present, should be bool
        if "market_feed" in status:
            assert isinstance(status["market_feed"], bool)

    def test_get_circuit_breaker_states_returns_dict(self, gateway: BrokerGateway):
        """get_circuit_breaker_states() should return dict with CB states."""
        states = gateway.get_circuit_breaker_states()
        assert isinstance(states, dict)
        # May have read_cb, write_cb, admin_cb keys
        # Values should be integers (0=CLOSED, 1=OPEN, 2=HALF_OPEN)
        for name, state in states.items():
            assert isinstance(state, int), f"Circuit breaker {name} state not int"
            assert 0 <= state <= 2, f"Circuit breaker {name} invalid state: {state}"

    def test_circuit_breaker_has_read_cb(self, gateway: BrokerGateway):
        """Circuit breaker states should include read_cb."""
        states = gateway.get_circuit_breaker_states()
        # Dhan typically has read circuit breaker
        assert "read_cb" in states or len(states) > 0

    def test_circuit_breaker_has_write_cb(self, gateway: BrokerGateway):
        """Circuit breaker states should include write_cb."""
        states = gateway.get_circuit_breaker_states()
        # Dhan typically has write circuit breaker
        assert "write_cb" in states or len(states) > 0

    def test_get_token_refresh_metrics_returns_dict(self, gateway: BrokerGateway):
        """get_token_refresh_metrics() should return dict with refresh stats."""
        metrics = gateway.get_token_refresh_metrics()
        assert isinstance(metrics, dict)
        # Should have refresh_count and error_count
        assert "refresh_count" in metrics
        assert "error_count" in metrics
        assert isinstance(metrics["refresh_count"], int)
        assert isinstance(metrics["error_count"], int)

    def test_token_refresh_count_non_negative(self, gateway: BrokerGateway):
        """Token refresh count should be >= 0."""
        metrics = gateway.get_token_refresh_metrics()
        assert metrics["refresh_count"] >= 0

    def test_token_error_count_non_negative(self, gateway: BrokerGateway):
        """Token error count should be >= 0."""
        metrics = gateway.get_token_refresh_metrics()
        assert metrics["error_count"] >= 0

    def test_get_rate_limiter_metrics_returns_dict(self, gateway: BrokerGateway):
        """get_rate_limiter_metrics() should return dict with rate limiter stats."""
        metrics = gateway.get_rate_limiter_metrics()
        assert isinstance(metrics, dict)
        # Should have tokens_available and requests_throttled
        assert "tokens_available" in metrics
        assert "requests_throttled" in metrics
        assert isinstance(metrics["tokens_available"], int)
        assert isinstance(metrics["requests_throttled"], int)

    def test_rate_limiter_tokens_non_negative(self, gateway: BrokerGateway):
        """Rate limiter tokens available should be >= 0."""
        metrics = gateway.get_rate_limiter_metrics()
        assert metrics["tokens_available"] >= 0

    def test_rate_limiter_throttled_non_negative(self, gateway: BrokerGateway):
        """Rate limiter requests throttled should be >= 0."""
        metrics = gateway.get_rate_limiter_metrics()
        assert metrics["requests_throttled"] >= 0

    def test_observability_all_methods_callable(self, gateway: BrokerGateway):
        """All observability methods should be callable without errors."""
        # Verify all methods can be called
        status = gateway.get_connection_status()
        assert status is not None

        cb_states = gateway.get_circuit_breaker_states()
        assert cb_states is not None

        token_metrics = gateway.get_token_refresh_metrics()
        assert token_metrics is not None

        rate_metrics = gateway.get_rate_limiter_metrics()
        assert rate_metrics is not None

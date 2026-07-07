"""Tests for BaseHttpClient — retry, token refresh, rate limiting, circuit breaker."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from brokers.infrastructure.http_client import (
    AuthenticationError,
    BaseHttpClient,
    HttpError,
    RateLimitError,
)
from brokers.infrastructure.rate_config import RateLimitConfig


def _mock_response(status_code: int = 200, json_data: dict | None = None, headers: dict | None = None):
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {"status": "success", "data": {}}
    resp.text = str(json_data) if json_data else "OK"
    resp.headers = headers or {}
    return resp


def _make_client(rate_config: RateLimitConfig | None = None, token_refresh_fn=None) -> BaseHttpClient:
    """Create a BaseHttpClient with a mock session."""
    session = MagicMock()
    session.headers = {}  # real dict so update_token works
    client = BaseHttpClient(
        base_url="https://api.example.com/v2",
        headers={"client-id": "test", "access-token": "tok"},
        rate_config=rate_config or RateLimitConfig(
            limits={"/orders": 0.04, "/marketfeed/quote": 1.0},
            read_prefixes=("/marketfeed/",),
            write_prefixes=("/orders",),
        ),
        max_retries=3,
        base_delay_ms=10,  # fast for tests
        max_delay_ms=50,
        token_refresh_fn=token_refresh_fn,
        session=session,
    )
    return client


class TestBasicRequests:
    def test_get_success(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(200, {"data": {"id": "123"}})
        result = client.get("/orders")
        assert result["data"]["id"] == "123"

    def test_post_success(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(200, {"status": "success"})
        result = client.post("/orders", json={"symbol": "RELIANCE"})
        assert result["status"] == "success"

    def test_put_success(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(200, {"status": "ok"})
        result = client.put("/orders/123", json={"quantity": 20})
        assert result["status"] == "ok"

    def test_delete_success(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(200, {"status": "deleted"})
        result = client.delete("/orders/123")
        assert result["status"] == "deleted"


class TestErrorHandling:
    def test_4xx_raises_immediately(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(400, {"error": "bad request"})
        with pytest.raises(HttpError, match="Client error"):
            client.get("/orders")

    def test_500_retries_then_succeeds(self):
        client = _make_client()
        client._session.request.side_effect = [
            _mock_response(500),
            _mock_response(500),
            _mock_response(200, {"data": "ok"}),
        ]
        result = client.get("/orders")
        assert result["data"] == "ok"
        assert client._session.request.call_count == 3

    def test_500_retries_then_fails(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(500)
        with pytest.raises(HttpError, match="Server error"):
            client.get("/orders")

    def test_network_error_retries(self):
        import requests

        client = _make_client()
        client._session.request.side_effect = [
            requests.RequestException("connection refused"),
            _mock_response(200, {"data": "ok"}),
        ]
        result = client.get("/orders")
        assert result["data"] == "ok"

    def test_network_error_exhausts_retries(self):
        import requests

        client = _make_client()
        client._session.request.side_effect = requests.RequestException("timeout")
        with pytest.raises(HttpError, match="Network error"):
            client.get("/orders")


class TestTokenRefresh:
    def test_401_triggers_refresh_then_retries(self):
        refresh_fn = MagicMock(return_value="new_token")
        client = _make_client(token_refresh_fn=refresh_fn)
        client._session.request.side_effect = [
            _mock_response(401),
            _mock_response(200, {"data": "ok"}),
        ]
        result = client.get("/orders")
        assert result["data"] == "ok"
        assert refresh_fn.called

    def test_401_no_refresh_fn_raises(self):
        client = _make_client(token_refresh_fn=None)
        client._session.request.return_value = _mock_response(401)
        with pytest.raises(AuthenticationError, match="Token rejected"):
            client.get("/orders")

    def test_401_refresh_fails_raises(self):
        refresh_fn = MagicMock(return_value=None)
        client = _make_client(token_refresh_fn=refresh_fn)
        client._session.request.return_value = _mock_response(401)
        with pytest.raises(AuthenticationError):
            client.get("/orders")

    def test_refresh_cooldown_prevents_rapid_refresh(self):
        refresh_fn = MagicMock(return_value="new_token")
        client = _make_client(token_refresh_fn=refresh_fn)
        # First call: refresh succeeds
        client._session.request.side_effect = [
            _mock_response(401),
            _mock_response(200, {"data": "ok"}),
        ]
        client.get("/orders")
        assert refresh_fn.call_count == 1
        # Second call: 401 again, but cooldown should prevent refresh
        client._session.request.side_effect = [_mock_response(401)]
        with pytest.raises(AuthenticationError):
            client.get("/orders")
        # refresh_fn was NOT called again (cooldown)
        assert refresh_fn.call_count == 1

    def test_update_token_updates_header(self):
        client = _make_client()
        client.update_token("new_tok")
        assert client._session.headers["access-token"] == "new_tok"


class TestRateLimiting:
    def test_429_retries_with_retry_after(self):
        client = _make_client()
        client._session.request.side_effect = [
            _mock_response(429, headers={"Retry-After": "0.01"}),
            _mock_response(200, {"data": "ok"}),
        ]
        result = client.get("/orders")
        assert result["data"] == "ok"

    def test_429_exhausts_retries(self):
        client = _make_client()
        client._session.request.return_value = _mock_response(429)
        with pytest.raises(RateLimitError, match="Rate limited"):
            client.get("/orders")

    def test_throttle_sleeps_for_slow_endpoints(self):
        """Quote endpoint has 1.0s interval — should sleep."""
        config = RateLimitConfig(
            limits={"/slow": 0.05},  # 50ms for test speed
        )
        client = _make_client(rate_config=config)
        client._session.request.return_value = _mock_response(200, {"data": "ok"})
        start = time.monotonic()
        client.get("/slow")
        client.get("/slow")  # second call should throttle
        elapsed = time.monotonic() - start
        assert elapsed >= 0.04  # should have waited ~50ms between calls


class TestCircuitBreaker:
    def test_cb_opens_after_threshold(self):
        client = _make_client()
        # Fail 5 times to open the circuit (default threshold=5)
        client._session.request.return_value = _mock_response(500)
        for _ in range(5):
            with pytest.raises(HttpError):
                client.get("/orders")
        # Circuit should now be open
        assert client.circuit_breaker_states["write"] == "open"
        # Next request should be blocked by CB
        with pytest.raises(HttpError, match="Circuit breaker open"):
            client.get("/orders")

    def test_cb_success_resets(self):
        client = _make_client()
        # Fail a few times
        client._session.request.side_effect = [
            _mock_response(500),
            _mock_response(500),
            _mock_response(200, {"data": "ok"}),
        ]
        client.get("/orders")
        assert client.circuit_breaker_states["write"] == "closed"

    def test_cb_categories_isolated(self):
        """A failure in 'write' should NOT open the 'read' circuit."""
        client = _make_client()
        # Fail write endpoint
        client._session.request.return_value = _mock_response(500)
        for _ in range(5):
            with pytest.raises(HttpError):
                client.post("/orders")
        # Write CB should be open
        assert client.circuit_breaker_states["write"] == "open"
        # Read CB should still be closed (isolated)
        assert client.circuit_breaker_states["read"] == "closed"

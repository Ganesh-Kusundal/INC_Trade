"""Tests for brokers.dhan.totp_client and token_scheduler.

Covers:
  - DhanTotpClient: login flow with mocked HTTP, cooldown enforcement, error handling
  - DhanTokenScheduler: start/stop, background refresh, backoff on rate limit
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
import requests

from brokers.common.auth.token_manager import (
    AuthManager,
    TokenSource,
    TokenState,
    TotpCooldownGuard,
)
from brokers.dhan.totp_client import (
    DhanTotpClient,
    DhanTotpError,
    TotpRateLimitError,
)
from brokers.dhan.token_scheduler import DhanTokenScheduler


# ── DhanTotpClient tests ───────────────────────────────────────────────────


class TestDhanTotpClient:
    def _make_mock_response(self, status: int = 200, data: dict | None = None) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = data or {"access_token": "tok_123", "expires_in": 300}
        resp.text = str(data or {})
        return resp

    @patch("brokers.dhan.totp_client.requests.post")
    def test_login_success(self, mock_post):
        mock_post.return_value = self._make_mock_response(200, {
            "access_token": "dhan_tok_abc",
            "expires_in": 300,
            "refresh_token": "refresh_xyz",
        })
        client = DhanTotpClient(cooldown=TotpCooldownGuard(cooldown_seconds=0))
        state = client.login("JBSWY3DPEHPK3PXP", "1234", "dhan_client_1")
        assert state.access_token == "dhan_tok_abc"
        assert state.source == TokenSource.TOTP
        assert state.broker_id == "dhan_client_1"
        assert state.is_valid

    @patch("brokers.dhan.totp_client.requests.post")
    def test_login_rate_limit(self, mock_post):
        mock_post.return_value = self._make_mock_response(429, {
            "errorMessage": "You can login once every 2 minutes",
        })
        client = DhanTotpClient(cooldown=TotpCooldownGuard(cooldown_seconds=0))
        with pytest.raises(TotpRateLimitError):
            client.login("JBSWY3DPEHPK3PXP", "1234", "dhan_client_1")

    @patch("brokers.dhan.totp_client.requests.post")
    def test_login_http_error(self, mock_post):
        mock_post.return_value = self._make_mock_response(500, {"error": "server"})
        client = DhanTotpClient(cooldown=TotpCooldownGuard(cooldown_seconds=0))
        with pytest.raises(DhanTotpError, match="HTTP 500"):
            client.login("JBSWY3DPEHPK3PXP", "1234", "dhan_client_1")

    @patch("brokers.dhan.totp_client.requests.post")
    def test_login_network_error(self, mock_post):
        mock_post.side_effect = requests.ConnectionError("network down")
        client = DhanTotpClient(cooldown=TotpCooldownGuard(cooldown_seconds=0))
        with pytest.raises(DhanTotpError, match="network"):
            client.login("JBSWY3DPEHPK3PXP", "1234", "dhan_client_1")

    @patch("brokers.dhan.totp_client.requests.post")
    def test_login_no_access_token(self, mock_post):
        mock_post.return_value = self._make_mock_response(200, {"foo": "bar"})
        client = DhanTotpClient(cooldown=TotpCooldownGuard(cooldown_seconds=0))
        with pytest.raises(DhanTotpError, match="no access token"):
            client.login("JBSWY3DPEHPK3PXP", "1234", "dhan_client_1")

    @patch("brokers.dhan.totp_client.requests.post")
    def test_cooldown_blocks_repeated_login(self, mock_post):
        # First login succeeds and resets cooldown
        mock_post.return_value = self._make_mock_response(200, {"access_token": "tok", "expires_in": 300})
        cooldown = TotpCooldownGuard(cooldown_seconds=300)
        client = DhanTotpClient(cooldown=cooldown)
        state = client.login("JBSWY3DPEHPK3PXP", "1234", "dhan_client_1")
        assert state.access_token == "tok"
        # Cooldown is reset on success, so manually record an attempt to simulate a failed attempt before
        cooldown.record_attempt()
        # Second login should be blocked by cooldown
        with pytest.raises(TotpRateLimitError, match="cooldown"):
            client.login("JBSWY3DPEHPK3PXP", "1234", "dhan_client_1")

    @patch("brokers.dhan.totp_client.requests.post")
    def test_refresh_calls_login_again(self, mock_post):
        mock_post.return_value = self._make_mock_response(200, {"access_token": "new_tok", "expires_in": 300})
        client = DhanTotpClient(cooldown=TotpCooldownGuard(cooldown_seconds=0))
        state = client.refresh("JBSWY3DPEHPK3PXP", "1234", "dhan_client_1")
        assert state.access_token == "new_tok"


# ── DhanTokenScheduler tests ───────────────────────────────────────────────


class TestDhanTokenScheduler:
    def test_start_and_stop(self):
        def acquire_fn() -> TokenState:
            return TokenState(access_token="tok", source=TokenSource.TOTP)

        manager = AuthManager(on_acquire=acquire_fn, broker_name="dhan")
        scheduler = DhanTokenScheduler(manager, check_interval=30)
        scheduler.start()
        assert scheduler.is_running is True
        time.sleep(0.1)  # Let it run briefly
        scheduler.stop(timeout=2.0)
        assert scheduler.is_running is False

    def test_refresh_now_success(self):
        call_count = [0]
        def acquire_fn() -> TokenState:
            call_count[0] += 1
            return TokenState(access_token=f"tok_{call_count[0]}", source=TokenSource.TOTP)

        manager = AuthManager(on_acquire=acquire_fn, broker_name="dhan")
        scheduler = DhanTokenScheduler(manager, check_interval=60)
        result = scheduler.refresh_now()
        assert result is True
        assert scheduler.refresh_count == 1

    def test_refresh_now_failure(self, monkeypatch):
        def acquire_fn() -> TokenState:
            raise ValueError("login failed")

        manager = AuthManager(on_acquire=acquire_fn, broker_name="dhan")
        scheduler = DhanTokenScheduler(manager, check_interval=60)
        monkeypatch.setattr(scheduler._stop_event, "wait", lambda *a, **kw: None)
        result = scheduler.refresh_now()
        assert result is False
        assert scheduler.error_count == 1
        assert scheduler.last_error is not None

    def test_initial_backoff(self):
        manager = AuthManager(broker_name="dhan")
        scheduler = DhanTokenScheduler(manager)
        assert scheduler.current_backoff == 120  # Initial

    def test_backoff_caps_at_max(self, monkeypatch):
        """Verify backoff doubles and caps at 600s without actually waiting."""
        def fail_acquire() -> TokenState:
            raise ValueError("fail")

        manager = AuthManager(on_acquire=fail_acquire, broker_name="dhan")
        scheduler = DhanTokenScheduler(manager, check_interval=30)
        # Prevent actual waiting during the test
        monkeypatch.setattr(scheduler._stop_event, "wait", lambda *a, **kw: None)
        # Trigger multiple failures
        for _ in range(10):
            scheduler.refresh_now()
        assert scheduler.current_backoff <= 600  # Max backoff
        assert scheduler.current_backoff == 600  # Should be exactly at cap

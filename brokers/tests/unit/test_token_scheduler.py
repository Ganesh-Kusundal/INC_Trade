"""Tests for token refresh scheduler."""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock


from brokers.adapters.dhan.auth import DhanAuth
from inc_trade.domain.exceptions import TokenRateLimitError
from inc_trade.infrastructure.storage.token_store import TokenSource, TokenState
from inc_trade.resilience.token_scheduler import TokenRefreshScheduler


class TestTokenRefreshScheduler:
    def _make_auth(self, valid=True):
        auth = MagicMock(spec=DhanAuth)
        if valid:
            auth.state = TokenState(
                access_token="test-token",
                source=TokenSource.TOTP,
                issued_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
            )
        else:
            auth.state = TokenState(
                access_token="test-token",
                source=TokenSource.TOTP,
                issued_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
        auth.generate_token.return_value = "new-token"
        return auth

    def test_start_and_stop(self):
        auth = self._make_auth()
        scheduler = TokenRefreshScheduler(auth, interval_seconds=1)
        scheduler.start()
        assert scheduler.is_running
        scheduler.stop()
        assert not scheduler.is_running

    def test_refresh_now(self):
        auth = self._make_auth(valid=False)
        scheduler = TokenRefreshScheduler(auth)
        result = scheduler.refresh_now()
        assert result
        auth.generate_token.assert_called_once()

    def test_on_refresh_callback(self):
        auth = self._make_auth(valid=False)
        received = []
        scheduler = TokenRefreshScheduler(
            auth, on_refresh=lambda t: received.append(t)
        )
        scheduler.refresh_now()
        assert received == ["new-token"]

    def test_skip_when_valid(self):
        auth = self._make_auth(valid=True)
        auth.generate_token = MagicMock()
        scheduler = TokenRefreshScheduler(auth)
        result = scheduler.refresh_now()
        assert result
        auth.generate_token.assert_not_called()

    def test_rate_limit_backoff(self):
        auth = self._make_auth(valid=False)
        auth.generate_token.side_effect = TokenRateLimitError("rate limited")
        scheduler = TokenRefreshScheduler(auth)
        result = scheduler.refresh_now()
        assert not result
        assert scheduler.health()["error_count"] == 1

    def test_refresh_lock_prevents_concurrent(self):
        auth = self._make_auth(valid=False)
        lock = threading.Lock()
        scheduler = TokenRefreshScheduler(auth, refresh_lock=lock)

        lock.acquire()
        result = scheduler.refresh_now()
        assert not result
        lock.release()

    def test_health_metrics(self):
        auth = self._make_auth(valid=False)
        scheduler = TokenRefreshScheduler(auth)
        scheduler.refresh_now()
        health = scheduler.health()
        assert health["refresh_count"] == 1
        assert health["is_running"] is False

    def test_error_count_on_failure(self):
        auth = self._make_auth(valid=False)
        auth.generate_token.side_effect = RuntimeError("fail")
        scheduler = TokenRefreshScheduler(auth)
        scheduler.refresh_now()
        assert scheduler.health()["error_count"] == 1

    def test_double_start_is_safe(self):
        auth = self._make_auth()
        scheduler = TokenRefreshScheduler(auth, interval_seconds=1)
        scheduler.start()
        scheduler.start()
        assert scheduler.is_running
        scheduler.stop()

    def test_stop_timeout(self):
        auth = self._make_auth()
        scheduler = TokenRefreshScheduler(auth, interval_seconds=1)
        scheduler.start()
        scheduler.stop(timeout_seconds=0.1)
        assert not scheduler.is_running

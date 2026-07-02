"""Unit tests for TokenRefreshScheduler."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from brokers.common.auth import AuthManager, TokenSource, TokenState
from brokers.dhan.token_scheduler import TokenRefreshScheduler


@pytest.fixture
def mock_auth():
    """Auth manager with an expired token (scheduler refresh path)."""
    auth = MagicMock(spec=AuthManager)
    auth.state = TokenState(
        access_token="expired_token",
        source=TokenSource.TOTP,
        issued_at=datetime.now() - timedelta(hours=2),
        expires_at=datetime.now() - timedelta(hours=1),
    )
    refreshed = TokenState(
        access_token="fresh_token",
        source=TokenSource.TOTP,
        issued_at=datetime.now(),
        expires_at=datetime.now() + timedelta(hours=1),
    )
    auth.acquire.return_value = refreshed
    return auth


@pytest.fixture
def valid_auth():
    """Auth manager with a still-valid token."""
    auth = MagicMock(spec=AuthManager)
    auth.state = TokenState(
        access_token="valid_token",
        source=TokenSource.TOTP,
        issued_at=datetime.now(),
        expires_at=datetime.now() + timedelta(hours=1),
    )
    return auth


class TestTokenRefreshScheduler:
    def test_start_creates_daemon_thread(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60)
        scheduler.start()
        assert scheduler.is_running
        scheduler.stop()

    def test_stop_joins_thread(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60)
        scheduler.start()
        assert scheduler.is_running
        scheduler.stop()
        assert not scheduler.is_running

    def test_start_idempotent(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60)
        scheduler.start()
        scheduler.start()
        assert scheduler.is_running
        scheduler.stop()

    def test_refresh_now_calls_acquire_when_expired(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60)
        result = scheduler.refresh_now()
        mock_auth.acquire.assert_called_once()
        assert result is True

    def test_refresh_now_calls_on_refresh(self, mock_auth):
        on_refresh = MagicMock()
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60, on_refresh=on_refresh)
        scheduler.refresh_now()
        on_refresh.assert_called_once_with("fresh_token")

    def test_refresh_now_skips_acquire_when_valid(self, valid_auth):
        scheduler = TokenRefreshScheduler(valid_auth, interval_seconds=60)
        result = scheduler.refresh_now()
        valid_auth.acquire.assert_not_called()
        assert result is True

    def test_refresh_now_returns_false_when_acquire_invalid(self, mock_auth):
        mock_auth.acquire.return_value = TokenState(
            access_token="",
            source=TokenSource.TOTP,
        )
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60)
        result = scheduler.refresh_now()
        assert result is False

    def test_refresh_now_handles_exception(self, mock_auth):
        mock_auth.acquire.side_effect = RuntimeError("auth error")
        on_error = MagicMock()
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60, on_error=on_error)
        result = scheduler.refresh_now()
        assert result is False
        on_error.assert_called_once()

    def test_background_refresh_increments_count(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=1)
        scheduler.start()
        time.sleep(0.3)
        scheduler.stop()
        assert scheduler.refresh_count >= 1

    def test_custom_interval(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=5)
        assert scheduler._interval == 5

    def test_refresh_count_starts_at_zero(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60)
        assert scheduler.refresh_count == 0

    def test_stop_when_not_started(self, mock_auth):
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60)
        scheduler.stop()

    def test_on_error_callback_on_failure(self, mock_auth):
        mock_auth.acquire.side_effect = RuntimeError("boom")
        on_error = MagicMock()
        scheduler = TokenRefreshScheduler(mock_auth, interval_seconds=60, on_error=on_error)
        scheduler.refresh_now()
        on_error.assert_called_once()

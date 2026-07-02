"""Tests for the LifecycleManager integration with TokenRefreshScheduler."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from brokers.dhan.token_scheduler import TokenRefreshScheduler
from infrastructure.lifecycle import HealthState, LifecycleManager


class _FakeAuth:
    """Minimal stand-in for AuthManager for scheduler tests."""

    def __init__(self, valid: bool = True) -> None:
        self._valid = valid
        self._state = MagicMock()
        self._state.access_token = "TOKEN"
        self._state.is_valid.return_value = valid
        self.acquire_calls = 0

    def acquire(self):
        self.acquire_calls += 1
        return self._state if self._valid else None

    @property
    def state(self):
        return self._state if self._valid else None


@pytest.fixture
def fake_auth() -> _FakeAuth:
    return _FakeAuth(valid=True)


def test_scheduler_starts_and_stops_via_lifecycle(fake_auth: _FakeAuth) -> None:
    mgr = LifecycleManager()
    scheduler = TokenRefreshScheduler(
        auth=fake_auth,  # type: ignore[arg-type]
        interval_seconds=3600,  # far away; we trigger manually
        buffer_seconds=300,
    )
    mgr.register(scheduler)
    mgr.start_all()
    assert scheduler.is_running
    mgr.stop_all()
    assert not scheduler.is_running


def test_scheduler_refresh_lock_is_shared_with_http_handler(
    fake_auth: _FakeAuth,
) -> None:
    """The lock the scheduler exposes must be the same object passed to
    the HTTP 401 handler — so both cannot refresh simultaneously."""
    shared_lock = threading.Lock()
    scheduler = TokenRefreshScheduler(
        auth=fake_auth,  # type: ignore[arg-type]
        interval_seconds=3600,
        refresh_lock=shared_lock,
    )
    assert scheduler.refresh_lock is shared_lock


def test_scheduler_health_reports_running_state(fake_auth: _FakeAuth) -> None:
    mgr = LifecycleManager()
    scheduler = TokenRefreshScheduler(
        auth=fake_auth,  # type: ignore[arg-type]
        interval_seconds=3600,
    )
    mgr.register(scheduler)
    snap_before = mgr.health_snapshot()
    assert snap_before["dhan.token_refresh_scheduler"]["state"] == HealthState.STOPPED.value
    mgr.start_all()
    snap_after = mgr.health_snapshot()
    assert snap_after["dhan.token_refresh_scheduler"]["state"] == HealthState.HEALTHY.value
    mgr.stop_all()


def test_scheduler_health_reports_degraded_after_error(fake_auth: _FakeAuth) -> None:
    mgr = LifecycleManager()
    scheduler = TokenRefreshScheduler(
        auth=fake_auth,  # type: ignore[arg-type]
        interval_seconds=3600,
    )
    mgr.register(scheduler)
    mgr.start_all()
    try:
        # Force an error
        scheduler._last_error = "test failure"
        health = scheduler.health()
        assert health.state == HealthState.DEGRADED
        assert "test failure" in health.detail
    finally:
        mgr.stop_all()


def test_scheduler_stop_drains_quickly(fake_auth: _FakeAuth) -> None:
    mgr = LifecycleManager(default_stop_timeout=0.2)
    scheduler = TokenRefreshScheduler(
        auth=fake_auth,  # type: ignore[arg-type]
        interval_seconds=3600,
    )
    mgr.register(scheduler)
    mgr.start_all()
    started = time.monotonic()
    mgr.stop_all()
    elapsed = time.monotonic() - started
    # Stop should return within the default timeout, not block forever.
    assert elapsed < 1.0


def test_scheduler_refresh_now_skips_when_token_valid(fake_auth: _FakeAuth) -> None:
    scheduler = TokenRefreshScheduler(
        auth=fake_auth,  # type: ignore[arg-type]
        interval_seconds=3600,
    )
    assert scheduler.refresh_now() is True
    assert fake_auth.acquire_calls == 0

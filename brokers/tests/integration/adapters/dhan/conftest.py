"""Fixtures for modern Dhan regression integration tests."""

from __future__ import annotations

import contextlib
import os
import time
from datetime import datetime, timezone
from datetime import time as dt_time
from pathlib import Path

import pytest
from inc_trade.infrastructure.credentials import CredentialResolver

from brokers.adapters.dhan.gateway import DhanGateway

_REPO_ROOT = Path(__file__).resolve().parents[5]
_INTEGRATION_DIR = Path(__file__).resolve().parent


def _env_path() -> Path:
    resolver = CredentialResolver(project_root=_REPO_ROOT)
    path = resolver.resolve_env_path("dhan")
    return path or _REPO_ROOT / ".env.local"


ENV_PATH = _env_path()

if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    CredentialResolver(project_root=_REPO_ROOT).load_broker_env("dhan")


def _has_live_credentials() -> bool:
    if not ENV_PATH.exists() or ENV_PATH.stat().st_size == 0:
        return False
    client_id = os.environ.get("DHAN_CLIENT_ID", "").strip()
    if not client_id:
        return False
    token = os.environ.get("DHAN_ACCESS_TOKEN", "").strip()
    pin = os.environ.get("DHAN_PIN", "").strip()
    totp = os.environ.get("DHAN_TOTP_SECRET", "").strip()
    return bool(token or (pin and totp))


def is_market_open() -> bool:
    """Return True if current IST time is within NSE trading hours (Mon-Fri)."""
    if os.environ.get("FORCE_MARKET_OPEN") == "1":
        return True
    ist = timezone(offset=__import__("datetime").timedelta(hours=5, minutes=30))
    now = datetime.now(ist)
    if now.weekday() >= 5:
        return False
    return dt_time(9, 15) <= now.time() <= dt_time(15, 30)


def require_market_hours():
    """Decorator factory that skips a test if the market is closed."""
    return pytest.mark.skipif(
        not is_market_open(),
        reason="Requires open market hours (or FORCE_MARKET_OPEN=1)",
    )


def _throttle_seconds() -> float:
    raw = os.environ.get("DHAN_TEST_THROTTLE_MS", "400")
    try:
        return max(0.0, int(raw) / 1000.0)
    except ValueError:
        return 0.2


@pytest.fixture(scope="session")
def live_gateway() -> DhanGateway:
    """Session-scoped DhanGateway for regression tests."""
    if not _has_live_credentials():
        pytest.skip(
            ".env.local with DHAN_CLIENT_ID and credentials required for Dhan regression"
        )

    access_token = os.environ.get("DHAN_ACCESS_TOKEN") or None
    gw = DhanGateway(
        access_token=access_token,
        client_id=os.environ.get("DHAN_CLIENT_ID"),
        pin=os.environ.get("DHAN_PIN"),
        totp_secret=os.environ.get("DHAN_TOTP_SECRET"),
        env_path=ENV_PATH,
        auto_refresh=True,
    )
    gw.instruments.load()
    yield gw
    with contextlib.suppress(Exception):
        gw.close()


@pytest.fixture(autouse=True)
def _rate_limit_throttle(request):
    """Throttle live regression calls to respect Dhan quote rate limits."""
    yield
    if request.node.get_closest_marker("regression"):
        delay = _throttle_seconds()
        if delay > 0:
            time.sleep(delay)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        try:
            path = Path(str(item.fspath)).resolve()
        except Exception:
            continue
        if _INTEGRATION_DIR not in path.parents:
            continue
        item.add_marker(pytest.mark.integration)
        item.add_marker(pytest.mark.dhan)

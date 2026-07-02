"""Shared fixtures and markers for Dhan live integration tests.

Every test module inside this directory is auto-tagged with the
``integration``, ``sandbox``, and ``dhan`` markers so that:

    pytest -m dhan                     — all Dhan tests
    pytest -m "dhan and regression"    — regression suite only
    pytest -m "dhan and off_market_safe" — REST-only, no creds for market hours
    pytest -m "dhan and market_hours"  — streaming tests (NSE hours only)
"""

from __future__ import annotations

import contextlib
import os
import threading
import time
from pathlib import Path

import pytest

from brokers.dhan.factory import BrokerFactory
from brokers.dhan.gateway import BrokerGateway

_INTEGRATION_DIR = Path(__file__).resolve().parent

# Project root .env.local
ENV_PATH = _INTEGRATION_DIR.parent.parent.parent.parent / ".env.local"

_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_PATH, override=True)
        _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))
    except ImportError:
        pass


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-tag every item in this directory with integration/sandbox/dhan."""
    for item in items:
        if _INTEGRATION_DIR not in Path(str(item.fspath)).resolve().parents:
            continue
        item.add_marker(pytest.mark.integration)
        item.add_marker(pytest.mark.sandbox)
        item.add_marker(pytest.mark.dhan)


# ---------------------------------------------------------------------------
# Session-scoped gateway — shared across all integration modules
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def live_gateway() -> BrokerGateway:
    """Session-scoped live BrokerGateway.

    Skipped automatically when .env.local is absent or has no DHAN_CLIENT_ID.
    Creating the gateway once per session loads the instrument CSV exactly
    once (~4 s) and reuses the HTTP connection pool for all integration tests.
    """
    if not _live_env_loaded:
        pytest.skip(".env.local with DHAN_CLIENT_ID required for live integration tests")

    gw = BrokerFactory().create(env_path=ENV_PATH, load_instruments=True)
    yield gw
    with contextlib.suppress(Exception):
        gw.close()


# ---------------------------------------------------------------------------
# Per-module variant (kept for backward-compat with existing test files that
# declare their own ``gateway`` fixture from this same factory pattern)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def gateway(live_gateway: BrokerGateway) -> BrokerGateway:
    """Module-scoped alias for live_gateway (backward-compatible)."""
    return live_gateway


# ---------------------------------------------------------------------------
# Rate-limit serializer
# Quote APIs are 1 req/s; apply a minimum inter-test gap so sequential
# integration tests do not trigger 429s while staying deterministic.
# ---------------------------------------------------------------------------

class _RateLimitSerializer:
    """Lightweight token-bucket enforcing 1 s minimum gap for quote endpoints."""

    QUOTE_INTERVAL = 1.05  # 1 req/s + 50 ms safety margin

    def __init__(self) -> None:
        self._last: float = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            elapsed = time.monotonic() - self._last
            if elapsed < self.QUOTE_INTERVAL:
                time.sleep(self.QUOTE_INTERVAL - elapsed)
            self._last = time.monotonic()


_quote_serializer = _RateLimitSerializer()


@pytest.fixture(autouse=True)
def _throttle_quote_calls(request: pytest.FixtureRequest) -> None:
    """Auto-use fixture that adds inter-test delay for live integration tests.

    Only active when the test is in the integration directory and the live env
    is loaded, so offline / unit tests are unaffected.
    """
    if not _live_env_loaded:
        return
    if _INTEGRATION_DIR not in Path(str(request.fspath)).resolve().parents:
        return
    _quote_serializer.wait()

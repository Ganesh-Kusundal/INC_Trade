"""Fixtures for the Dhan regression test package.

Provides the session-scoped ``live_gateway`` fixture used by
``test_regression_suite.py``, ``test_e2e_smoke.py``, and any future
tests in this directory.

The fixture is intentionally lightweight: it delegates to
``BrokerFactory`` (same as the integration conftest) and auto-skips
when ``.env.local`` is missing.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import pytest

from brokers.dhan.factory import BrokerFactory
from brokers.dhan.gateway import BrokerGateway

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
ENV_PATH = _PROJECT_ROOT / ".env.local"

_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_PATH, override=True)
        _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))
    except ImportError:
        pass


@pytest.fixture(scope="session")
def live_gateway() -> BrokerGateway:
    """Session-scoped live BrokerGateway for regression tests.

    Skipped automatically when .env.local is absent or has no DHAN_CLIENT_ID.
    """
    if not _live_env_loaded:
        pytest.skip(
            ".env.local with DHAN_CLIENT_ID required for Dhan regression tests"
        )

    gw = BrokerFactory().create(env_path=ENV_PATH, load_instruments=True)
    yield gw
    with contextlib.suppress(Exception):
        gw.close()

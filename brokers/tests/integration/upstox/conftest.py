"""Shared fixtures for modern Upstox live integration tests."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from brokers.infrastructure.credentials import CredentialResolver

_REPO_ROOT = Path(__file__).resolve().parents[4]
_INTEGRATION_DIR = Path(__file__).resolve().parent


def _env_path() -> Path:
    resolver = CredentialResolver(project_root=_REPO_ROOT)
    path = resolver.resolve_env_path("upstox")
    return path or _REPO_ROOT / ".env.upstox"


ENV_PATH = _env_path()

if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    CredentialResolver(project_root=_REPO_ROOT).load_broker_env("upstox")


def _has_live_credentials() -> bool:
    if not ENV_PATH.exists() or ENV_PATH.stat().st_size == 0:
        return False
    client_id = (
        os.environ.get("UPSTOX_CLIENT_ID", "").strip()
        or os.environ.get("UPSTOX_API_KEY", "").strip()
    )
    if not client_id:
        return False
    auth_mode = os.environ.get("UPSTOX_AUTH_MODE", "STATIC").strip().upper()
    if auth_mode == "TOTP":
        mobile = os.environ.get("UPSTOX_MOBILE", "").strip()
        pin = os.environ.get("UPSTOX_PIN", "").strip()
        secret = os.environ.get("UPSTOX_TOTP_SECRET", "").strip()
        return bool(mobile and pin and secret)
    return bool(os.environ.get("UPSTOX_ACCESS_TOKEN", "").strip())


def _should_skip_live() -> bool:
    if not _has_live_credentials():
        return True
    if os.environ.get("UPSTOX_INTEGRATION") != "1":
        return True
    env = os.environ.get("UPSTOX_ENVIRONMENT", "LIVE").strip().upper()
    if env not in ("LIVE", "SANDBOX"):
        return True
    if os.environ.get("FORCE_MARKET_OPEN") == "1":
        return False
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        if now.weekday() >= 5:
            return True
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return not (market_open <= now <= market_close)
    except Exception:
        return False


def _should_skip_pre_prod() -> bool:
    if _should_skip_live():
        return True
    return os.environ.get("PRE_PROD_GATE", "0") != "1"


skip_live = pytest.mark.skipif(
    _should_skip_live(),
    reason=(
        "Live tests need UPSTOX_INTEGRATION=1, credentials in .env.upstox, "
        "market hours (or FORCE_MARKET_OPEN=1)"
    ),
)

requires_pre_prod = pytest.mark.skipif(
    _should_skip_pre_prod(),
    reason="Requires PRE_PROD_GATE=1 plus live Upstox credentials",
)


@pytest.fixture(scope="session")
def gateway():
    from dataclasses import replace

    from brokers.adapters.upstox.auth.config import UpstoxSettingsLoader
    from brokers.adapters.upstox.gateway import UpstoxGateway

    settings = UpstoxSettingsLoader.from_env()
    settings = replace(
        settings,
        analytics_only=False,
        access_token="",
        allow_live_orders=False,
    )
    gw = UpstoxGateway(settings=settings, auto_refresh=True, load_instruments=True)
    yield gw
    gw.close()


@pytest.fixture
def ws_teardown(gateway):
    yield
    gateway.streaming.stop()
    gateway.portfolio_stream.stop()


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        try:
            path = Path(str(item.fspath)).resolve()
        except Exception:
            continue
        if _INTEGRATION_DIR not in path.parents:
            continue
        item.add_marker(pytest.mark.integration)
        item.add_marker(pytest.mark.upstox)

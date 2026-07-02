from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.auth.json_token_state_store import JsonTokenStateStore
from brokers.upstox.auth.token_manager import UpstoxTokenManager


def _settings(tmp_path: Path, **overrides) -> UpstoxConnectionSettings:
    base = {
        "client_id": "CID",
        "client_secret": "CSEC",
        "access_token": "initial-access",
        "refresh_token": "initial-refresh",
        "token_state_file": tmp_path / "upstox-token.json",
        "refresh_buffer_minutes": 30,
    }
    base.update(overrides)
    return UpstoxConnectionSettings(**base)


def test_initial_holder_is_static():
    s = _settings_simple()
    mgr = UpstoxTokenManager(settings=s, oauth_client=MagicMock())
    assert mgr.bearer_token() == "initial-access"


def test_bootstrap_loads_persisted_state(tmp_path):
    path = tmp_path / "upstox-token.json"
    future_exp = int(time.time() * 1000) + 3600 * 1000
    path.write_text(
        json.dumps(
            {
                "access_token": "persisted-access",
                "refresh_token": "persisted-refresh",
                "expires_at_ms": future_exp,
                "issued_at_ms": int(time.time() * 1000),
                "source": "OAUTH",
            }
        )
    )
    s = _settings(tmp_path)
    mgr = UpstoxTokenManager(
        settings=s, oauth_client=MagicMock(), state_store=JsonTokenStateStore(path)
    )
    state = mgr.bootstrap()
    assert state.access_token == "persisted-access"
    assert state.refresh_token == "persisted-refresh"
    assert mgr.bearer_token() == "persisted-access"


def test_bootstrap_falls_back_to_settings_when_no_persisted(tmp_path):
    s = _settings(tmp_path)
    oauth = MagicMock()
    oauth.fetch_profile.return_value = -1
    mgr = UpstoxTokenManager(
        settings=s, oauth_client=oauth, state_store=JsonTokenStateStore(s.token_state_file)
    )
    state = mgr.bootstrap()
    assert state.access_token == "initial-access"
    assert state.refresh_token == "initial-refresh"
    assert state.expires_at_ms > int(time.time() * 1000)


def test_upgrade_from_webhook_replaces_when_fresher():
    s = _settings_simple()
    mgr = UpstoxTokenManager(settings=s, oauth_client=MagicMock())
    now = int(time.time() * 1000)
    applied = mgr.upgrade_from_webhook("webhook-token", expires_at_ms=now + 7200 * 1000)
    assert applied is True
    assert mgr.bearer_token() == "webhook-token"


def test_upgrade_from_webhook_rejects_stale_token():
    s = _settings_simple()
    mgr = UpstoxTokenManager(settings=s, oauth_client=MagicMock())
    now = int(time.time() * 1000)
    mgr._state = None
    mgr.upgrade_from_webhook("newer-token", expires_at_ms=now + 7200 * 1000)
    applied = mgr.upgrade_from_webhook("older-token", expires_at_ms=now + 60 * 1000)
    assert applied is False
    assert mgr.bearer_token() == "newer-token"


def test_upgrade_from_webhook_rejects_blank_or_zero():
    s = _settings_simple()
    mgr = UpstoxTokenManager(settings=s, oauth_client=MagicMock())
    with pytest.raises(ValueError):
        mgr.upgrade_from_webhook("", expires_at_ms=int(time.time() * 1000) + 1000)
    with pytest.raises(ValueError):
        mgr.upgrade_from_webhook("token", expires_at_ms=0)


def test_invalidate_policy_keeps_unexpired_token():
    s = _settings_simple()
    oauth = MagicMock()
    oauth.fetch_profile.return_value = -1
    mgr = UpstoxTokenManager(settings=s, oauth_client=oauth)
    mgr.bootstrap()
    assert mgr.invalidate() is False


def _settings_simple() -> UpstoxConnectionSettings:
    return UpstoxConnectionSettings(
        client_id="CID",
        client_secret="CSEC",
        access_token="initial-access",
        refresh_token="initial-refresh",
        token_state_file=None,
        refresh_buffer_minutes=30,
    )

"""Tests for validate-before-generate Dhan bootstrap policy."""

from __future__ import annotations

import base64
import json
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from brokers.common.auth import JsonTokenStateStore, TokenSource, TokenState
from brokers.dhan.factory import BrokerFactory


def _make_jwt(payload: dict) -> str:
    header = base64.b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
    body = base64.b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    signature = base64.b64encode(b"fakesignature").decode().rstrip("=")
    return f"{header}.{body}.{signature}"


@pytest.fixture
def env_file(tmp_path):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    path = tmp_path / ".env.local"
    path.write_text(
        f"DHAN_CLIENT_ID=TEST_CLIENT\n"
        f"DHAN_PIN=1234\n"
        f"DHAN_TOTP_SECRET=JBSWY3DPEHPK3PXP\n"
        f"DHAN_TOKEN_STATE_DIR={runtime}\n"
        f"DHAN_ACCESS_TOKEN=\n"
    )
    return path


def test_bootstrap_reuses_valid_json_token_without_totp(env_file, tmp_path):
    runtime = tmp_path / "runtime"

    valid_token = _make_jwt({"exp": int(time.time()) + 7200})
    store = JsonTokenStateStore(runtime / "dhan-token-state.json")
    store.save(
        TokenState(
            access_token=valid_token,
            source=TokenSource.TOTP,
            expires_at=datetime.now() + timedelta(hours=2),
        )
    )

    totp_calls = {"count": 0}

    def fake_generate(_settings=None):
        totp_calls["count"] += 1
        return "should-not-be-called"

    with patch("brokers.dhan.factory._generate_totp_token", fake_generate):
        factory = BrokerFactory()
        auth, token = factory._create_auth(
            __import__(
                "brokers.dhan.settings", fromlist=["DhanSettingsLoader"]
            ).DhanSettingsLoader.from_env(env_path=env_file),
            env_file,
        )

    assert totp_calls["count"] == 0
    assert token == valid_token
    assert auth.state is not None
    assert auth.state.access_token == valid_token


def test_bootstrap_generates_once_when_token_expired(env_file, tmp_path):
    runtime = tmp_path / "runtime"

    expired_token = _make_jwt({"exp": int(time.time()) - 60})
    store = JsonTokenStateStore(runtime / "dhan-token-state.json")
    store.save(
        TokenState(
            access_token=expired_token,
            source=TokenSource.TOTP,
            expires_at=datetime.now() - timedelta(minutes=1),
        )
    )

    fresh_token = _make_jwt({"exp": int(time.time()) + 7200})
    totp_calls = {"count": 0}

    def fake_generate(_settings=None):
        totp_calls["count"] += 1
        return fresh_token

    with patch("brokers.dhan.factory._generate_totp_token", fake_generate):
        factory = BrokerFactory()
        auth, token = factory._create_auth(
            __import__(
                "brokers.dhan.settings", fromlist=["DhanSettingsLoader"]
            ).DhanSettingsLoader.from_env(env_path=env_file),
            env_file,
        )

    assert totp_calls["count"] == 1
    assert token == fresh_token
    assert auth.state.access_token == fresh_token

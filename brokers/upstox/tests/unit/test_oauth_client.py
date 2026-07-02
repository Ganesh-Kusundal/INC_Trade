from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.upstox.auth.exceptions import UpstoxAuthError
from brokers.upstox.auth.oauth_client import TokenResponse, UpstoxOAuthClient


def _oauth() -> UpstoxOAuthClient:
    return UpstoxOAuthClient(base_url="https://api.upstox.com")


def test_exchange_code_uses_authorization_code_grant():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "access_token": "at-xyz",
        "refresh_token": "rt-abc",
        "expires_in": 86400,
    }
    session.post.return_value = resp
    client = UpstoxOAuthClient(base_url="https://api.upstox.com")
    client._session = session
    out = client.exchange_code(
        code="code-1",
        client_id="CID",
        client_secret="CSEC",
        redirect_uri="http://localhost:18080/cb",
        code_verifier="verifier-xyz",
    )
    assert isinstance(out, TokenResponse)
    assert out.access_token == "at-xyz"
    assert out.refresh_token == "rt-abc"
    call = session.post.call_args
    assert "/v2/login/authorization/token" in call.args[0]
    assert "grant_type=authorization_code" in call.kwargs["data"]
    assert "code=code-1" in call.kwargs["data"]


def test_refresh_token_uses_refresh_token_grant():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "access_token": "at-new",
        "refresh_token": "rt-new",
        "expires_in": 86400,
    }
    session.post.return_value = resp
    client = UpstoxOAuthClient(base_url="https://api.upstox.com")
    client._session = session
    out = client.refresh_token("rt-old", "CID", "CSEC")
    assert out.access_token == "at-new"
    body = session.post.call_args.kwargs["data"]
    assert "grant_type=refresh_token" in body
    assert "refresh_token=rt-old" in body


def test_exchange_code_raises_on_non_2xx():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 400
    resp.text = "bad request"
    session.post.return_value = resp
    client = UpstoxOAuthClient(base_url="https://api.upstox.com")
    client._session = session
    with pytest.raises(UpstoxAuthError):
        client.exchange_code("c", "CID", "CSEC", "http://x", "v")


def test_trigger_token_request_posts_to_v3():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "status": "success",
        "data": {
            "authorization_expiry": "1740729366039",
            "notifier_url": "https://example.com/webhook",
        },
    }
    session.post.return_value = resp
    client = UpstoxOAuthClient(base_url="https://api.upstox.com")
    client._session = session
    out = client.trigger_token_request("CID", "CSEC")
    assert out["authorizationExpiry"] == "1740729366039"
    assert out["notifierUrl"] == "https://example.com/webhook"
    assert "/v3/login/auth/token/request/CID" in session.post.call_args.args[0]


def test_fetch_profile_returns_token_expiry_epoch_ms():
    from datetime import datetime, timezone

    iso = datetime(2026, 5, 1, 3, 30, tzinfo=timezone.utc).isoformat()
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"status": "success", "data": {"token_expiry": iso}}
    session.get.return_value = resp
    client = UpstoxOAuthClient(base_url="https://api.upstox.com")
    client._session = session
    exp_ms = client.fetch_profile("at")
    assert exp_ms > 0


def test_fetch_profile_returns_minus_one_on_missing_token_expiry():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"status": "success", "data": {}}
    session.get.return_value = resp
    client = UpstoxOAuthClient(base_url="https://api.upstox.com")
    client._session = session
    assert client.fetch_profile("at") == -1


def test_validate_read_only_token_returns_true_on_200():
    session = MagicMock()
    resp = MagicMock()
    resp.status_code = 200
    session.get.return_value = resp
    client = UpstoxOAuthClient(base_url="https://api.upstox.com")
    client._session = session
    assert client.validate_read_only_token("at") is True

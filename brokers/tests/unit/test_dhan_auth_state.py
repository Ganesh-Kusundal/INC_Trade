"""Tests for enhanced DhanAuth with state tracking."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brokers.adapters.dhan.auth import DhanAuth
from inc_trade.domain.exceptions import AuthenticationError, TokenRateLimitError
from inc_trade.infrastructure.storage.token_store import TokenSource


@pytest.fixture(autouse=True)
def _mock_totp_cooldown(monkeypatch):
    from inc_trade.infrastructure.totp_cooldown import TOTPCooldown
    monkeypatch.setattr(TOTPCooldown, "check_allowed", lambda self: None)
    monkeypatch.setattr(TOTPCooldown, "remaining_cooldown_seconds", lambda self: 0.0)
    TOTPCooldown._instances.clear()


class TestDhanAuth:
    def test_init_with_static_token(self):
        auth = DhanAuth(access_token="test-token", client_id="test-client")
        assert auth.get_token() == "test-token"
        assert auth.is_authenticated()
        assert auth.state is not None
        assert auth.state.source == TokenSource.STATIC

    def test_init_without_token(self):
        auth = DhanAuth(client_id="test-client")
        assert auth.get_token() == ""
        assert not auth.is_authenticated()

    @patch("brokers.adapters.dhan.auth.requests.post")
    def test_generate_token_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {"accessToken": "generated-token"}
        }
        mock_post.return_value = mock_resp

        auth = DhanAuth(
            client_id="test-client",
            pin="1234",
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        token = auth.generate_token()
        assert token == "generated-token"
        assert auth.state is not None
        assert auth.state.source == TokenSource.TOTP

    @patch("brokers.adapters.dhan.auth.requests.post")
    def test_generate_token_rate_limit(self, mock_post):
        success_resp = MagicMock()
        success_resp.status_code = 200
        success_resp.json.return_value = {"data": {"accessToken": "initial-token"}}

        rate_limit_resp = MagicMock()
        rate_limit_resp.status_code = 400
        rate_limit_resp.text = "Token can be generated once every 2 minutes"

        mock_post.side_effect = [success_resp, rate_limit_resp]

        auth = DhanAuth(
            client_id="test-client",
            pin="1234",
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        with pytest.raises(TokenRateLimitError):
            auth.generate_token()

    @patch("brokers.adapters.dhan.auth.requests.post")
    def test_generate_token_auth_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Invalid credentials"
        mock_post.return_value = mock_resp

        auth = DhanAuth(access_token="initial-token", client_id="test-client")
        with pytest.raises(AuthenticationError):
            auth.generate_token()

    def test_is_valid_with_valid_state(self):
        auth = DhanAuth(access_token="test-token", client_id="test-client")
        assert auth.is_valid()

    def test_is_valid_without_token(self):
        auth = DhanAuth(client_id="test-client")
        assert not auth.is_valid()

    @patch("brokers.adapters.dhan.auth.requests.post")
    def test_refresh_token_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {"accessToken": "refreshed-token"}
        }
        mock_post.return_value = mock_resp

        auth = DhanAuth(
            client_id="test-client",
            pin="1234",
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        token = auth.refresh_token()
        assert token == "refreshed-token"

    def test_refresh_token_without_totp(self):
        auth = DhanAuth(access_token="test-token", client_id="test-client")
        token = auth.refresh_token()
        assert token == "test-token"

    @patch("brokers.adapters.dhan.auth.requests.post")
    def test_acquire_success(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {"accessToken": "acquired-token"}
        }
        mock_post.return_value = mock_resp

        auth = DhanAuth(
            client_id="test-client",
            pin="1234",
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        state = auth.acquire()
        assert state is not None
        assert state.access_token == "acquired-token"

    @patch("brokers.adapters.dhan.auth.requests.post")
    def test_acquire_failure_returns_none(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Invalid"
        mock_post.return_value = mock_resp

        auth = DhanAuth(access_token="initial", client_id="test-client")
        state = auth.acquire()
        assert state is None

    @patch("brokers.adapters.dhan.auth.requests.post")
    def test_force_refresh(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {"accessToken": "new-token"}
        }
        mock_post.return_value = mock_resp

        auth = DhanAuth(
            client_id="test-client",
            pin="1234",
            totp_secret="JBSWY3DPEHPK3PXP",
        )
        state = auth.force_refresh()
        assert state is not None
        assert state.access_token == "new-token"

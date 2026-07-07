"""Tests for brokers.upstox.totp_client and token_manager.

Covers:
  - UpstoxTotpClient: login flow with mocked HTTP, cooldown, error handling
  - UpstoxTokenManager: bootstrap, ensure_valid, bearer_token
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests

from brokers.common.auth.credential_resolver import UpstoxCredentials
from brokers.common.auth.token_manager import (
    TokenSource,
    TotpCooldownGuard,
)
from brokers.upstox.totp_client import (
    UpstoxTotpClient,
    UpstoxTotpError,
    UpstoxTotpRateLimitError,
)


# ── UpstoxTotpClient tests ─────────────────────────────────────────────────


class TestUpstoxTotpClient:
    def _make_mock_response(self, status: int = 200, data: dict | None = None) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = data or {"access_token": "up_tok", "expires_in": 86400}
        resp.text = str(data or {})
        return resp

    @patch("brokers.upstox.totp_client.requests.post")
    def test_login_success(self, mock_post):
        mock_post.return_value = self._make_mock_response(200, {
            "access_token": "upstox_tok_abc",
            "expires_in": 86400,
            "refresh_token": "refresh_xyz",
        })
        client = UpstoxTotpClient(api_key="test_key", cooldown=TotpCooldownGuard(cooldown_seconds=0))
        state = client.login("JBSWY3DPEHPK3PXP", "1234", "+919876543210")
        assert state.access_token == "upstox_tok_abc"
        assert state.source == TokenSource.TOTP
        assert state.is_valid

    @patch("brokers.upstox.totp_client.requests.post")
    def test_login_rate_limit(self, mock_post):
        mock_post.return_value = self._make_mock_response(429, {
            "error": "Too many attempts",
        })
        client = UpstoxTotpClient(cooldown=TotpCooldownGuard(cooldown_seconds=0))
        with pytest.raises(UpstoxTotpRateLimitError):
            client.login("JBSWY3DPEHPK3PXP", "1234", "+919876543210")

    @patch("brokers.upstox.totp_client.requests.post")
    def test_login_http_error(self, mock_post):
        mock_post.return_value = self._make_mock_response(500, {"error": "server"})
        client = UpstoxTotpClient(cooldown=TotpCooldownGuard(cooldown_seconds=0))
        with pytest.raises(UpstoxTotpError, match="HTTP 500"):
            client.login("JBSWY3DPEHPK3PXP", "1234", "+919876543210")

    @patch("brokers.upstox.totp_client.requests.post")
    def test_login_network_error(self, mock_post):
        mock_post.side_effect = requests.ConnectionError("network down")
        client = UpstoxTotpClient(cooldown=TotpCooldownGuard(cooldown_seconds=0))
        with pytest.raises(UpstoxTotpError, match="network"):
            client.login("JBSWY3DPEHPK3PXP", "1234", "+919876543210")

    @patch("brokers.upstox.totp_client.requests.post")
    def test_login_no_access_token(self, mock_post):
        mock_post.return_value = self._make_mock_response(200, {"foo": "bar"})
        client = UpstoxTotpClient(cooldown=TotpCooldownGuard(cooldown_seconds=0))
        with pytest.raises(UpstoxTotpError, match="no access token"):
            client.login("JBSWY3DPEHPK3PXP", "1234", "+919876543210")

    @patch("brokers.upstox.totp_client.requests.post")
    def test_cooldown_blocks_repeated_login(self, mock_post):
        mock_post.return_value = self._make_mock_response(200, {"access_token": "tok", "expires_in": 300})
        cooldown = TotpCooldownGuard(cooldown_seconds=300)
        client = UpstoxTotpClient(cooldown=cooldown)
        state = client.login("JBSWY3DPEHPK3PXP", "1234", "+919876543210")
        assert state.access_token == "tok"
        # Cooldown is reset on success, so manually record to simulate a prior failed attempt
        cooldown.record_attempt()
        with pytest.raises(UpstoxTotpRateLimitError, match="cooldown"):
            client.login("JBSWY3DPEHPK3PXP", "1234", "+919876543210")

    @patch("brokers.upstox.totp_client.requests.post")
    def test_refresh_calls_login_again(self, mock_post):
        mock_post.return_value = self._make_mock_response(200, {"access_token": "new_tok", "expires_in": 300})
        client = UpstoxTotpClient(cooldown=TotpCooldownGuard(cooldown_seconds=0))
        state = client.refresh("JBSWY3DPEHPK3PXP", "1234", "+919876543210")
        assert state.access_token == "new_tok"


# ── UpstoxTokenManager tests ───────────────────────────────────────────────
#
# NOTE: UpstoxTokenManager was removed (brokers/upstox/token_manager.py) in
# favor of the shared brokers/common/auth AuthManager + scheduler wired in
# Platform. Token lifecycle is now owned by the common AuthManager; the
# UpstoxProvider.update_token method is the receiver the scheduler calls.

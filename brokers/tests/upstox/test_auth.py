"""Tests for brokers.upstox.totp_client — upstox-totp library wrapper.

Covers:
  - UpstoxOAuthClient: wraps upstox-totp library for automated login
  - UpstoxTotpClient: backward-compatible alias
  - Cooldown guard behaviour
  - Error handling and rate limiting
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brokers.common.auth.token_manager import (
    TokenSource,
    TotpCooldownGuard,
)
from brokers.upstox.totp_client import (
    UpstoxOAuthClient,
    UpstoxTotpClient,
    UpstoxTotpError,
    UpstoxTotpRateLimitError,
)


# ── UpstoxOAuthClient tests ────────────────────────────────────────────────


class TestUpstoxOAuthClient:
    def _make_client(self, **kwargs) -> UpstoxOAuthClient:
        defaults = dict(
            api_key="test_key",
            api_secret="test_secret",
            redirect_uri="http://127.0.0.1:18080/callback",
            username="9999999999",
            password="testpass",
            pin="123456",
            totp_secret="JBSWY3DPEHPK3PXP",
            cooldown=TotpCooldownGuard(cooldown_seconds=0),
        )
        defaults.update(kwargs)
        return UpstoxOAuthClient(**defaults)

    def _make_mock_response(self, success: bool = True, access_token: str = "tok") -> MagicMock:
        """Create a mock upstox-totp response."""
        response = MagicMock()
        response.success = success
        if success:
            response.data = MagicMock()
            response.data.access_token = access_token
            response.data.user_name = "TESTUSER"
        else:
            response.data = None
            response.error = {"message": "Login failed", "errorCode": "UDAPI100001"}
        return response

    @patch("brokers.upstox.totp_client.UpstoxTOTP", create=True)
    def test_login_success(self, mock_totp_cls):
        """Login succeeds and returns valid TokenState."""
        # Mock the upstox-totp library
        mock_client = MagicMock()
        mock_client.app_token.get_access_token.return_value = self._make_mock_response(
            success=True, access_token="upstox_tok_abc"
        )
        mock_totp_cls.return_value = mock_client

        client = self._make_client()

        # Patch the import inside _initialize_client
        with patch.dict("sys.modules", {"upstox_totp": MagicMock(UpstoxTOTP=mock_totp_cls)}):
            state = client.login()

        assert state.access_token == "upstox_tok_abc"
        assert state.source == TokenSource.TOTP
        assert state.is_valid

    def test_login_missing_credentials(self):
        """Login raises when credentials are invalid."""
        client = self._make_client(username="", password="")

        # The upstox-totp library will fail with UDAPI100068 when redirect_uri
        # doesn't match the registered one, or with other auth errors
        with pytest.raises(UpstoxTotpError):
            client.login()

    def test_cooldown_blocks_repeated_login(self):
        """Cooldown prevents rapid repeated login attempts."""
        cooldown = TotpCooldownGuard(cooldown_seconds=300)
        client = self._make_client(cooldown=cooldown)
        cooldown.record_attempt()
        with pytest.raises(UpstoxTotpRateLimitError, match="cooldown"):
            client.login()

    def test_extract_error_message_dict(self):
        """Extract error message from dict response."""
        response = MagicMock()
        response.error = {"message": "Invalid credentials", "errorCode": "UDAPI100069"}
        msg = UpstoxOAuthClient._extract_error_message(response)
        assert "Invalid credentials" in msg
        assert "UDAPI100069" in msg

    def test_extract_error_message_none(self):
        """Extract error message when no error present."""
        response = MagicMock()
        response.error = None
        msg = UpstoxOAuthClient._extract_error_message(response)
        assert msg == "Unknown error"

    def test_is_rate_limit_error_true(self):
        """Detect rate limit error correctly."""
        assert UpstoxOAuthClient._is_rate_limit_error(
            "UDAPI100500: You have exceeded the maximum number of requests"
        )
        assert UpstoxOAuthClient._is_rate_limit_error(
            "Too many request please try again later"
        )

    def test_is_rate_limit_error_false(self):
        """Non-rate-limit errors return False."""
        assert not UpstoxOAuthClient._is_rate_limit_error("Invalid credentials")
        assert not UpstoxOAuthClient._is_rate_limit_error("UDAPI100069")


# ── UpstoxTotpClient backward-compat alias ─────────────────────────────────


class TestUpstoxTotpClientAlias:
    """The old UpstoxTotpClient is now an alias for UpstoxOAuthClient."""

    def test_is_subclass_of_oauth_client(self):
        assert issubclass(UpstoxTotpClient, UpstoxOAuthClient)

    def test_can_instantiate_with_old_params(self):
        """Old-style params are accepted but ignored."""
        client = UpstoxTotpClient(
            api_key="k",
            api_secret="s",
            redirect_uri="http://127.0.0.1:18080/callback",
            username="9999999999",
            password="pass",
            pin="1234",
            totp_secret="JBSWY3DPEHPK3PXP",
            cooldown=TotpCooldownGuard(cooldown_seconds=0),
        )
        assert isinstance(client, UpstoxOAuthClient)

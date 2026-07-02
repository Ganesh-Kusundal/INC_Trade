"""Unit tests for Upstox TOTP bootstrap integration."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.auth.exceptions import UpstoxAuthError
from brokers.upstox.auth.token_manager import UpstoxTokenManager


def _make_settings(**kwargs) -> UpstoxConnectionSettings:
    """Create test settings with defaults."""
    defaults = {
        "client_id": "test-client-id",
        "client_secret": "test-secret",
        "redirect_uri": "http://localhost:18080",
        "auth_mode": "TOTP",
        "mobile": "9876543210",
        "pin": "123456",
        "totp_secret": "JBSWY3DPEHPK3PXP",
        "access_token": "",
        "refresh_token": "",
    }
    defaults.update(kwargs)
    return UpstoxConnectionSettings(**defaults)


class TestTotpBootstrap:
    """Test TOTP bootstrap flow."""

    @patch("brokers.upstox.auth.token_manager.UpstoxTotpClient")
    @patch("brokers.upstox.auth.token_manager.JwtExpiry")
    def test_bootstrap_totp_reuses_persisted_token(self, mock_jwt_expiry, mock_totp_client_class):
        """Persisted valid token should skip TOTP generation."""
        settings = _make_settings()
        mock_jwt_expiry.parse_expiry_epoch_ms.return_value = 9999999999999

        mock_store = MagicMock()
        mock_store.load.return_value = {
            "access_token": "persisted-token",
            "refresh_token": None,
            "expires_at_ms": 9999999999999,
            "issued_at_ms": 1000,
            "source": "TOTP",
        }

        token_manager = UpstoxTokenManager(settings, state_store=mock_store)
        state = token_manager.bootstrap()

        assert state.access_token == "persisted-token"
        mock_totp_client_class.assert_not_called()

    @patch("brokers.upstox.auth.token_manager.UpstoxTotpClient")
    @patch("brokers.upstox.auth.token_manager.JwtExpiry")
    def test_bootstrap_totp_success(self, mock_jwt_expiry, mock_totp_client_class):
        """Test successful TOTP bootstrap."""
        settings = _make_settings()

        # Mock TOTP client
        mock_totp_client = MagicMock()
        mock_totp_client.validate_config.return_value = True
        mock_totp_client.generate_token.return_value = {
            "access_token": "test-token",
            "user_name": "test-user",
            "success": True,
        }
        mock_totp_client_class.return_value = mock_totp_client

        # Mock JWT expiry
        mock_jwt_expiry.parse_expiry_epoch_ms.return_value = 9999999999999

        token_manager = UpstoxTokenManager(settings)
        state = token_manager.bootstrap()

        assert state.source == "TOTP"
        assert state.access_token == "test-token"
        assert state.refresh_token is None

    @patch("brokers.upstox.auth.token_manager.UpstoxTotpClient")
    def test_bootstrap_totp_invalid_config(self, mock_totp_client_class):
        """Test TOTP bootstrap with invalid config."""
        settings = _make_settings(mobile="")

        mock_totp_client = MagicMock()
        mock_totp_client.validate_config.return_value = False
        mock_totp_client_class.return_value = mock_totp_client

        token_manager = UpstoxTokenManager(settings)

        with pytest.raises(UpstoxAuthError, match="TOTP configuration incomplete"):
            token_manager.bootstrap()

    @patch("brokers.upstox.auth.token_manager.UpstoxTotpClient")
    def test_bootstrap_totp_with_refresh_token_fallback(self, mock_totp_client_class):
        """TOTP bootstrap may fall back only to an explicit OAuth refresh token."""
        settings = _make_settings(
            access_token="existing-token",
            refresh_token="existing-refresh-token",
        )
        oauth = MagicMock()
        oauth.fetch_profile.return_value = -1

        mock_totp_client = MagicMock()
        mock_totp_client.generate_token.side_effect = Exception("TOTP failed")
        mock_totp_client_class.return_value = mock_totp_client

        token_manager = UpstoxTokenManager(settings, oauth_client=oauth)

        # Should fall back to existing token
        state = token_manager.bootstrap()
        assert state.access_token == "existing-token"

    @patch("brokers.upstox.auth.token_manager.UpstoxTotpClient")
    def test_bootstrap_totp_does_not_reuse_env_access_token(self, mock_totp_client_class):
        """TOTP mode must not silently reuse stale UPSTOX_ACCESS_TOKEN values."""
        settings = _make_settings(access_token="stale-env-token", refresh_token="")

        mock_totp_client = MagicMock()
        mock_totp_client.generate_token.side_effect = Exception("TOTP failed")
        mock_totp_client_class.return_value = mock_totp_client

        token_manager = UpstoxTokenManager(settings)

        with pytest.raises(UpstoxAuthError, match="TOTP authentication failed"):
            token_manager.bootstrap()

    @patch("brokers.upstox.auth.token_manager.UpstoxTotpClient")
    def test_bootstrap_totp_no_fallback_raises(self, mock_totp_client_class):
        """Test TOTP bootstrap raises when no fallback available."""
        settings = _make_settings(
            access_token="",
            refresh_token="",
        )

        mock_totp_client = MagicMock()
        mock_totp_client.generate_token.side_effect = Exception("TOTP failed")
        mock_totp_client_class.return_value = mock_totp_client

        token_manager = UpstoxTokenManager(settings)

        with pytest.raises(UpstoxAuthError, match="TOTP authentication failed"):
            token_manager.bootstrap()

    @patch("brokers.upstox.auth.token_manager.UpstoxTotpClient")
    def test_try_refresh_on_401_reuses_in_memory_valid_token(self, mock_totp_client_class):
        """Transient 401 should not trigger a fresh TOTP login when token is still valid."""
        settings = _make_settings()
        token_manager = UpstoxTokenManager(settings, state_store=MagicMock())
        state = token_manager._from_persisted(
            {
                "access_token": "still-valid-token",
                "refresh_token": None,
                "expires_at_ms": 9_999_999_999_999,
                "issued_at_ms": 1_000,
                "source": "TOTP",
            }
        )
        token_manager._apply_token_state(state, label="Upstox token (test)")

        assert token_manager.try_refresh_on_401() is True
        assert token_manager.current_token() == "still-valid-token"
        mock_totp_client_class.assert_not_called()


class TestTotpModeDetection:
    """Test TOTP mode detection in settings."""

    def test_is_totp_true(self):
        """Test is_totp property returns True for TOTP mode."""
        settings = _make_settings(auth_mode="TOTP")
        assert settings.is_totp is True

    def test_is_totp_false(self):
        """Test is_totp property returns False for other modes."""
        settings = _make_settings(auth_mode="STATIC")
        assert settings.is_totp is False

    def test_has_totp_config_true(self):
        """Test has_totp_config returns True when all fields present."""
        settings = _make_settings()
        assert settings.has_totp_config is True

    def test_has_totp_config_false_missing_mobile(self):
        """Test has_totp_config returns False when mobile missing."""
        settings = _make_settings(mobile="")
        assert settings.has_totp_config is False

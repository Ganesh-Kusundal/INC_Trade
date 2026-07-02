"""Unit tests for Upstox TOTP client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brokers.common.auth.totp_cooldown import TotpRateLimitError
from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.auth.totp_client import UpstoxTotpClient


def _make_settings(**kwargs) -> UpstoxConnectionSettings:
    """Create test settings with defaults."""
    defaults = {
        "client_id": "test-client-id",
        "client_secret": "test-secret",
        "redirect_uri": "http://localhost:18080",
        "mobile": "9876543210",
        "pin": "123456",
        "totp_secret": "JBSWY3DPEHPK3PXP",
    }
    defaults.update(kwargs)
    return UpstoxConnectionSettings(**defaults)


@pytest.fixture(autouse=True)
def _disable_totp_cooldown(monkeypatch):
    """Isolate unit tests from process-wide TOTP cooldown state."""
    guard = MagicMock()
    guard.check_allowed.return_value = None
    monkeypatch.setattr(
        "brokers.common.auth.totp_cooldown.TotpCooldownGuard.for_broker",
        lambda *args, **kwargs: guard,
    )


class TestUpstoxTotpClientInitialization:
    """Test TOTP client initialization."""

    def test_init_with_valid_config(self):
        """Test client initializes successfully with valid config."""
        settings = _make_settings()
        with patch("upstox_totp.UpstoxTOTP") as mock_totp:
            mock_totp.return_value = MagicMock()
            client = UpstoxTotpClient(settings)
            assert client._client is not None

    def test_init_missing_library_raises(self):
        """Test initialization fails gracefully if library not installed."""
        settings = _make_settings()
        with (
            patch.dict("sys.modules", {"upstox_totp": None}),
            pytest.raises(RuntimeError, match="upstox-totp library is required"),
        ):
            UpstoxTotpClient(settings)


class TestUpstoxTotpClientTokenGeneration:
    """Test TOTP token generation."""

    def test_generate_token_success(self):
        """Test successful token generation."""
        settings = _make_settings()
        with patch("upstox_totp.UpstoxTOTP") as mock_totp:
            mock_response = MagicMock()
            mock_response.success = True
            mock_response.data = MagicMock()
            mock_response.data.access_token = "test-access-token"
            mock_response.data.user_name = "test-user"

            mock_client = MagicMock()
            mock_client.app_token.get_access_token.return_value = mock_response
            mock_totp.return_value = mock_client

            client = UpstoxTotpClient(settings)
            result = client.generate_token()

            assert result["success"] is True
            assert result["access_token"] == "test-access-token"
            assert result["user_name"] == "test-user"

    def test_generate_token_failure(self):
        """Test token generation failure handling."""
        settings = _make_settings()
        with patch("upstox_totp.UpstoxTOTP") as mock_totp:
            mock_response = MagicMock()
            mock_response.success = False
            mock_response.data = None

            mock_client = MagicMock()
            mock_client.app_token.get_access_token.return_value = mock_response
            mock_totp.return_value = mock_client

            client = UpstoxTotpClient(settings)

            with pytest.raises(RuntimeError, match="TOTP token generation failed"):
                client.generate_token()

    def test_generate_token_exception(self):
        """Test exception during token generation."""
        settings = _make_settings()
        with patch("upstox_totp.UpstoxTOTP") as mock_totp:
            mock_client = MagicMock()
            mock_client.app_token.get_access_token.side_effect = Exception("API error")
            mock_totp.return_value = mock_client

            client = UpstoxTotpClient(settings)

            with pytest.raises(RuntimeError, match="TOTP token generation failed"):
                client.generate_token()

    def test_generate_token_records_upstox_lockout(self, monkeypatch):
        """Broker-side Upstox OTP lockout must become a local cooldown."""
        settings = _make_settings()
        guard = MagicMock()
        guard.check_allowed.return_value = None
        monkeypatch.setattr(
            "brokers.common.auth.totp_cooldown.TotpCooldownGuard.for_broker",
            lambda *args, **kwargs: guard,
        )

        with patch("upstox_totp.UpstoxTOTP") as mock_totp:
            mock_client = MagicMock()
            mock_client.app_token.get_access_token.side_effect = Exception(
                "UDAPI100500: You have exceeded the maximum number of times you can "
                "generate an OTP. Kindly, try again after 10 mins."
            )
            mock_totp.return_value = mock_client

            client = UpstoxTotpClient(settings)

            with pytest.raises(TotpRateLimitError):
                client.generate_token()

        guard.record_rate_limited.assert_called_once()


class TestUpstoxTotpClientValidation:
    """Test TOTP configuration validation."""

    def test_validate_config_complete(self):
        """Test validation passes with complete config."""
        settings = _make_settings()
        with patch("upstox_totp.UpstoxTOTP"):
            client = UpstoxTotpClient(settings)
            assert client.validate_config() is True

    def test_validate_config_missing_mobile(self):
        """Test validation fails with missing mobile."""
        settings = _make_settings(mobile="")
        with patch("upstox_totp.UpstoxTOTP"):
            client = UpstoxTotpClient(settings)
            assert client.validate_config() is False

    def test_validate_config_missing_pin(self):
        """Test validation fails with missing PIN."""
        settings = _make_settings(pin="")
        with patch("upstox_totp.UpstoxTOTP"):
            client = UpstoxTotpClient(settings)
            assert client.validate_config() is False

    def test_validate_config_missing_totp_secret(self):
        """Test validation fails with missing TOTP secret."""
        settings = _make_settings(totp_secret="")
        with patch("upstox_totp.UpstoxTOTP"):
            client = UpstoxTotpClient(settings)
            assert client.validate_config() is False

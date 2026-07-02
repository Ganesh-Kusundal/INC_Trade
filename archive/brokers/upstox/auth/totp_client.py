"""Upstox TOTP client — automated token generation via upstox-totp library.

This module provides a clean wrapper around the upstox-totp library for
automated token generation without manual browser intervention.

Usage::

    from brokers.upstox.auth.totp_client import UpstoxTotpClient
    from brokers.upstox.auth.config import UpstoxConnectionSettings

    settings = UpstoxSettingsLoader.from_env()
    client = UpstoxTotpClient(settings)
    token = client.generate_token()
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class UpstoxTotpClient:
    """Automated Upstox token generation using TOTP (Time-based One-Time Password).

    Wraps the upstox-totp library to provide:
    - Token generation using mobile, PIN, and TOTP secret
    - Environment variable configuration
    - Error handling with graceful degradation
    """

    def __init__(self, settings: Any) -> None:
        """Initialize TOTP client with connection settings.

        Args:
            settings: UpstoxConnectionSettings with mobile, pin, and totp_secret populated
        """
        self._settings = settings
        self._client = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the upstox-totp client with explicit credentials."""
        try:
            from pydantic import SecretStr
            from upstox_totp import UpstoxTOTP

            self._client = UpstoxTOTP(
                username=self._settings.mobile,
                # The current upstox-totp login path only uses pin_code for
                # 2FA, but password is required by its config model.
                password=SecretStr(self._settings.pin),
                pin_code=SecretStr(self._settings.pin),
                totp_secret=SecretStr(self._settings.totp_secret),
                client_id=self._settings.client_id,
                client_secret=SecretStr(self._settings.client_secret),
                redirect_uri=self._settings.redirect_uri,
                debug=False,
            )
            logger.info("Upstox TOTP client initialized successfully")
        except ImportError as exc:
            logger.error("upstox-totp library not installed: %s", exc)
            raise RuntimeError(
                "upstox-totp library is required for TOTP auth mode. "
                "Install with: pip install upstox-totp"
            ) from exc
        except Exception as exc:
            logger.error("Failed to initialize Upstox TOTP client: %s", exc)
            raise

    def generate_token(self) -> dict[str, Any]:
        """Generate a new access token using TOTP.

        Returns:
            Dictionary with token information:
            - access_token: The generated access token
            - user_name: Upstox username
            - success: Boolean indicating success

        Raises:
            RuntimeError: If token generation fails
        """
        if not self._client:
            raise RuntimeError("TOTP client not initialized")

        from brokers.common.auth.totp_cooldown import TotpCooldownGuard, TotpRateLimitError

        guard = TotpCooldownGuard.for_broker("upstox")
        guard.check_allowed()
        guard.record_attempt()

        try:
            response = self._client.app_token.get_access_token()

            if response.success and response.data:
                guard.record_success()
                logger.info(
                    "TOTP token generated successfully for user: %s", response.data.user_name
                )
                return {
                    "access_token": response.data.access_token,
                    "user_name": response.data.user_name,
                    "success": True,
                }
            error_msg = self._response_error_message(response) or "TOTP token generation failed"
            if self._is_rate_limit_error(error_msg):
                guard.record_rate_limited()
                raise TotpRateLimitError(error_msg)
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        except TotpRateLimitError:
            raise
        except Exception as exc:
            if self._is_rate_limit_error(exc):
                guard.record_rate_limited()
                raise TotpRateLimitError(str(exc)) from exc
            logger.error("TOTP token generation error: %s", exc)
            raise RuntimeError(f"TOTP token generation failed: {exc}") from exc

    @staticmethod
    def _response_error_message(response: Any) -> str:
        error = getattr(response, "error", None)
        if not error:
            return ""
        if isinstance(error, dict):
            parts = [
                str(error.get("message") or ""),
                str(error.get("code") or error.get("errorCode") or ""),
            ]
            return " ".join(part for part in parts if part)
        return str(error)

    @staticmethod
    def _is_rate_limit_error(exc: object) -> bool:
        text = str(exc).lower()
        return (
            "udapi100500" in text
            and ("maximum number" in text or "10 min" in text or "generate an otp" in text)
        ) or "too many request" in text

    def validate_config(self) -> bool:
        """Validate that all required TOTP configuration is present.

        Returns:
            True if all required fields are populated
        """
        required = {
            "client_id": self._settings.client_id,
            "client_secret": self._settings.client_secret,
            "mobile": self._settings.mobile,
            "pin": self._settings.pin,
            "totp_secret": self._settings.totp_secret,
        }

        missing = [key for key, value in required.items() if not value]
        if missing:
            logger.warning("Missing TOTP configuration: %s", ", ".join(missing))
            return False

        return True

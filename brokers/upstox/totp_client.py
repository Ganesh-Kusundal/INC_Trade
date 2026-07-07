"""Upstox TOTP client — automated token generation via upstox-totp library.

Wraps the ``upstox-totp`` library for fully automated, headless token
generation — no browser, no manual mobile approval, no webhook server.

This is the same pattern used by the Trade_XV2 reference implementation.

Usage::

    from brokers.upstox.totp_client import UpstoxOAuthClient
    from brokers.common.auth.credential_resolver import CredentialResolver

    creds = CredentialResolver.for_upstox()
    client = UpstoxOAuthClient(
        api_key=creds.api_key,
        api_secret=creds.api_secret,
        redirect_uri=creds.redirect_uri,
        username=creds.username,
        password=creds.password,
        pin=creds.pin,
        totp_secret=creds.totp_secret,
    )
    token_state = client.login()
    print(token_state.access_token)
"""

from __future__ import annotations

import logging
from typing import Any

from brokers.common.auth.token_state import (
    TokenSource,
    TokenState,
)
from brokers.common.auth.totp import (
    TotpCooldownGuard,
)

logger = logging.getLogger(__name__)


# ── Exceptions ─────────────────────────────────────────────────────────────


class UpstoxTotpError(Exception):
    """Base exception for Upstox authentication errors."""


UpstoxAuthError = UpstoxTotpError


class UpstoxTotpRateLimitError(UpstoxTotpError):
    """Raised when Upstox enforces a rate-limit / cooldown period."""


UpstoxRateLimitError = UpstoxTotpRateLimitError


# ── Upstox TOTP client (wraps upstox-totp library) ────────────────────────


class UpstoxOAuthClient:
    """Automated Upstox token generation using the upstox-totp library.

    Wraps ``upstox_totp.UpstoxTOTP`` to provide:
    - Fully automated headless login (mobile + PIN + TOTP)
    - No browser, no manual mobile approval, no webhook server
    - Token returned synchronously in the response
    - Cooldown guard to prevent rate limiting

    This is the same pattern used by the Trade_XV2 reference implementation.
    """

    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        redirect_uri: str,
        username: str = "",
        password: str = "",
        pin: str = "",
        totp_secret: str = "",
        cooldown: TotpCooldownGuard | None = None,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._redirect_uri = redirect_uri
        self._username = username
        self._password = password
        self._pin = pin
        self._totp_secret = totp_secret
        self._timeout = timeout
        self._cooldown = cooldown or TotpCooldownGuard(
            cooldown_seconds=30,
            persist_path="runtime/upstox-oauth-cooldown.json",
        )
        self._client: Any = None

    def _initialize_client(self) -> None:
        """Initialize the upstox-totp client with credentials."""
        try:
            from pydantic import SecretStr
            from upstox_totp import UpstoxTOTP

            self._client = UpstoxTOTP(
                username=self._username,
                password=SecretStr(self._password or self._pin),
                pin_code=SecretStr(self._pin),
                totp_secret=SecretStr(self._totp_secret),
                client_id=self._api_key,
                client_secret=SecretStr(self._api_secret),
                redirect_uri=self._redirect_uri,
                debug=False,
            )
            logger.info("upstox_totp_client_initialized")
        except ImportError as exc:
            raise UpstoxTotpError(
                "upstox-totp library is required for automated login. "
                "Install with: pip install upstox-totp"
            ) from exc
        except Exception as exc:
            raise UpstoxTotpError(
                f"Failed to initialize Upstox TOTP client: {exc}"
            ) from exc

    def login(self) -> TokenState:
        """Generate a new access token using TOTP.

        Returns:
            TokenState with access_token and expiry.

        Raises:
            UpstoxTotpRateLimitError: If Upstox enforces a cooldown.
            UpstoxTotpError: If token generation fails.
        """
        if not self._cooldown.can_generate():
            remaining = self._cooldown.seconds_until_allowed()
            raise UpstoxTotpRateLimitError(
                f"Upstox cooldown active. Wait {remaining:.0f}s before retrying."
            )

        self._cooldown.record_attempt()

        # Initialize the upstox-totp client
        self._initialize_client()

        try:
            # Call the upstox-totp library's token generation
            response = self._client.app_token.get_access_token()

            if response.success and response.data:
                self._cooldown.reset()
                logger.info(
                    "upstox_login_success",
                    extra={"user_name": response.data.user_name},
                )
                return TokenState.from_expiry_seconds(
                    access_token=response.data.access_token,
                    expires_in_seconds=86400,  # Upstox tokens expire in 24h
                    source=TokenSource.TOTP,
                    broker_id="upstox",
                )

            # Handle error response
            error_msg = self._extract_error_message(response)
            if self._is_rate_limit_error(error_msg):
                raise UpstoxTotpRateLimitError(
                    f"Upstox rate-limited: {error_msg}"
                )
            raise UpstoxTotpError(f"Upstox login failed: {error_msg}")

        except UpstoxTotpError:
            raise
        except Exception as exc:
            if self._is_rate_limit_error(str(exc)):
                raise UpstoxTotpRateLimitError(
                    f"Upstox rate-limited: {exc}"
                ) from exc
            raise UpstoxTotpError(f"Upstox login failed: {exc}") from exc

    def refresh(self) -> TokenState:
        """Refresh by generating a new token.

        Upstox tokens expire after 24 hours with no refresh_token support.
        A full re-login is required.
        """
        return self.login()

    # ── Internal helpers ─────────────────────────────────────────────────

    @staticmethod
    def _extract_error_message(response: Any) -> str:
        """Extract error message from upstox-totp response."""
        error = getattr(response, "error", None)
        if not error:
            return "Unknown error"
        if isinstance(error, dict):
            parts = [
                str(error.get("message") or ""),
                str(error.get("code") or error.get("errorCode") or ""),
            ]
            return " ".join(part for part in parts if part)
        return str(error)

    @staticmethod
    def _is_rate_limit_error(text: str) -> bool:
        """Check if error text indicates rate limiting."""
        text_lower = text.lower()
        return (
            "udapi100500" in text_lower
            and ("maximum number" in text_lower or "10 min" in text_lower or "generate an otp" in text_lower)
        ) or "too many request" in text_lower


# ── Backward-compatible alias ──────────────────────────────────────────────


class UpstoxTotpClient(UpstoxOAuthClient):
    """Backward-compatible alias for :class:`UpstoxOAuthClient`.

    .. deprecated::
        Use ``UpstoxOAuthClient`` directly.
    """

    def login(  # type: ignore[override]
        self,
        totp_secret: str = "",
        pin: str = "",
        mobile: str = "",
    ) -> TokenState:
        """Perform headless login. Old params are accepted but ignored."""
        return super().login()

    def refresh(  # type: ignore[override]
        self,
        totp_secret: str = "",
        pin: str = "",
        mobile: str = "",
    ) -> TokenState:
        """Perform headless refresh. Old params are accepted but ignored."""
        return super().refresh()


__all__ = [
    "UpstoxOAuthClient",
    "UpstoxTotpClient",
    "UpstoxTotpError",
    "UpstoxAuthError",
    "UpstoxTotpRateLimitError",
    "UpstoxRateLimitError",
]

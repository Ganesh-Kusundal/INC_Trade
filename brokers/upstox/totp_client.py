"""Upstox TOTP client — performs TOTP-based login to obtain access tokens.

Upstox's TOTP authentication flow:
1. Generate a TOTP code from the shared secret
2. POST to Upstox's token endpoint with mobile, pin, and totp
3. Receive access_token + expires_in

Usage::

    from brokers.upstox.totp_client import UpstoxTotpClient
    from brokers.common.auth.credential_resolver import CredentialResolver

    creds = CredentialResolver.for_upstox()
    client = UpstoxTotpClient(api_key=creds.api_key)
    token_state = client.login(creds.totp_secret, creds.pin, creds.mobile)
    print(token_state.access_token)
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from brokers.common.auth.token_manager import (
    TokenSource,
    TokenState,
    TotpCooldownGuard,
    TotpGenerator,
)

logger = logging.getLogger(__name__)


# ── Exceptions ─────────────────────────────────────────────────────────────


class UpstoxTotpError(Exception):
    """Base exception for Upstox TOTP errors."""


class UpstoxTotpRateLimitError(UpstoxTotpError):
    """Raised when Upstox enforces a TOTP cooldown period."""


# ── Upstox TOTP client ─────────────────────────────────────────────────────


class UpstoxTotpClient:
    """Upstox TOTP-based authentication client.

    Performs the Upstox login flow:
      POST https://api.upstox.com/v2/login/authorization/mobile/totp
      Body: {"mobile_number": "...", "pin": "...", "totp": "..."}
      Query: ?api_key=...

    Returns a TokenState with the access token and expiry.
    """

    TOKEN_URL = "https://api.upstox.com/v2/login/authorization/mobile/totp"

    def __init__(
        self,
        *,
        api_key: str = "",
        token_url: str | None = None,
        cooldown: TotpCooldownGuard | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._api_key = api_key
        self._token_url = token_url or self.TOKEN_URL
        self._timeout = timeout
        self._cooldown = cooldown or TotpCooldownGuard(
            cooldown_seconds=60,
            persist_path="runtime/upstox-totp-cooldown.json",
        )

    def login(
        self,
        totp_secret: str,
        pin: str,
        mobile: str,
    ) -> TokenState:
        """Perform TOTP login and return a TokenState.

        Args:
            totp_secret: Base32-encoded TOTP shared secret.
            pin: Upstox account PIN (4 or 6 digits).
            mobile: Registered mobile number (e.g. "+919876543210").

        Returns:
            TokenState with access_token and expiry.

        Raises:
            UpstoxTotpRateLimitError: If Upstox enforces a cooldown.
            UpstoxTotpError: If login fails for any other reason.
        """
        if not self._cooldown.can_generate():
            remaining = self._cooldown.seconds_until_allowed()
            raise UpstoxTotpRateLimitError(
                f"Upstox TOTP cooldown active. Wait {remaining:.0f}s before retrying."
            )

        # Generate TOTP code
        totp_code = TotpGenerator.code_now(totp_secret)
        logger.debug("upstox_totp_generated")

        self._cooldown.record_attempt()

        # POST to token endpoint
        payload = {
            "mobile_number": mobile,
            "pin": pin,
            "totp": totp_code,
        }

        params = {"api_key": self._api_key} if self._api_key else {}

        try:
            response = requests.post(
                self._token_url,
                json=payload,
                params=params,
                timeout=self._timeout,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
        except requests.RequestException as exc:
            raise UpstoxTotpError(f"Upstox token request failed: {exc}") from exc

        if response.status_code != 200:
            body_text = response.text.lower()
            if "rate limit" in body_text or "too many" in body_text:
                raise UpstoxTotpRateLimitError(
                    f"Upstox rate-limited TOTP login: {response.text[:200]}"
                )
            raise UpstoxTotpError(
                f"Upstox login failed (HTTP {response.status_code}): {response.text[:200]}"
            )

        data: dict[str, Any] = response.json()
        access_token = str(data.get("access_token", data.get("accessToken", "")))
        if not access_token:
            raise UpstoxTotpError(f"Upstox login returned no access token: {data}")

        expires_in = int(data.get("expires_in", data.get("expiresIn", 86400)))
        refresh_token = str(data.get("refresh_token", data.get("refreshToken", "")))

        self._cooldown.reset()

        logger.info("upstox_login_success", extra={"expires_in": expires_in})

        return TokenState.from_expiry_seconds(
            access_token=access_token,
            expires_in_seconds=expires_in,
            refresh_token=refresh_token,
            source=TokenSource.TOTP,
            broker_id="upstox",
        )

    def refresh(
        self,
        totp_secret: str,
        pin: str,
        mobile: str,
    ) -> TokenState:
        """Refresh by performing a new TOTP login."""
        return self.login(totp_secret, pin, mobile)


__all__ = ["UpstoxTotpClient", "UpstoxTotpError", "UpstoxTotpRateLimitError"]

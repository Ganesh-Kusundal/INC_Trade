"""Dhan TOTP client — performs TOTP-based login to obtain access tokens.

Dhan's authentication flow:
1. Generate a TOTP code from the shared secret
2. POST to Dhan's token endpoint with clientId, pin, and totp
3. Receive access_token + expires_in

Usage::

    from brokers.dhan.totp_client import DhanTotpClient
    from brokers.common.auth.credential_resolver import CredentialResolver

    creds = CredentialResolver.for_dhan()
    client = DhanTotpClient()
    token_state = client.login(creds.totp_secret, creds.pin, creds.client_id)
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


class DhanTotpError(Exception):
    """Base exception for Dhan TOTP errors."""


class TotpRateLimitError(DhanTotpError):
    """Raised when Dhan enforces a TOTP cooldown period."""


# ── Dhan TOTP client ───────────────────────────────────────────────────────


class DhanTotpClient:
    """Dhan TOTP-based authentication client.

    Performs the Dhan login flow:
      POST https://api.dhan.co/v2/auth/token
      Body: {"dhanClientId": "...", "pin": "...", "totp": "..."}

    Returns a TokenState with the access token and expiry.
    """

    TOKEN_URL = "https://api.dhan.co/v2/auth/token"

    def __init__(
        self,
        *,
        token_url: str | None = None,
        cooldown: TotpCooldownGuard | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._token_url = token_url or self.TOKEN_URL
        self._timeout = timeout
        self._cooldown = cooldown or TotpCooldownGuard(
            cooldown_seconds=120,
            persist_path="runtime/dhan-totp-cooldown.json",
        )

    def login(
        self,
        totp_secret: str,
        pin: str,
        client_id: str,
    ) -> TokenState:
        """Perform TOTP login and return a TokenState.

        Args:
            totp_secret: Base32-encoded TOTP shared secret.
            pin: Dhan account PIN (4 or 6 digits).
            client_id: Dhan client ID.

        Returns:
            TokenState with access_token, refresh_token (if any), and expiry.

        Raises:
            TotpRateLimitError: If Dhan enforces a cooldown period.
            DhanTotpError: If login fails for any other reason.
        """
        # Check cooldown
        if not self._cooldown.can_generate():
            remaining = self._cooldown.seconds_until_allowed()
            raise TotpRateLimitError(
                f"Dhan TOTP cooldown active. Wait {remaining:.0f}s before retrying."
            )

        # Generate TOTP code
        totp_code = TotpGenerator.code_now(totp_secret)
        logger.debug("dhan_totp_generated", extra={"client_id": client_id})

        # Record attempt before the API call (so cooldown applies even on network errors)
        self._cooldown.record_attempt()

        # POST to token endpoint
        payload = {
            "dhanClientId": client_id,
            "pin": pin,
            "totp": totp_code,
        }

        try:
            response = requests.post(
                self._token_url,
                json=payload,
                timeout=self._timeout,
                headers={"Content-Type": "application/json"},
            )
        except requests.RequestException as exc:
            raise DhanTotpError(f"Dhan token request failed: {exc}") from exc

        if response.status_code != 200:
            # Check for rate limit in response body
            body_text = response.text.lower()
            if "once every 2 minutes" in body_text or "rate limit" in body_text:
                raise TotpRateLimitError(
                    f"Dhan rate-limited TOTP login: {response.text[:200]}"
                )
            raise DhanTotpError(
                f"Dhan login failed (HTTP {response.status_code}): {response.text[:200]}"
            )

        data: dict[str, Any] = response.json()
        access_token = str(data.get("access_token", data.get("accessToken", "")))
        if not access_token:
            raise DhanTotpError(f"Dhan login returned no access token: {data}")

        expires_in = int(data.get("expires_in", data.get("expiresIn", 300)))
        refresh_token = str(data.get("refresh_token", data.get("refreshToken", "")))

        # Reset cooldown on success
        self._cooldown.reset()

        logger.info(
            "dhan_login_success",
            extra={
                "client_id": client_id,
                "expires_in": expires_in,
            },
        )

        return TokenState.from_expiry_seconds(
            access_token=access_token,
            expires_in_seconds=expires_in,
            refresh_token=refresh_token,
            source=TokenSource.TOTP,
            broker_id=client_id,
        )

    def refresh(
        self,
        totp_secret: str,
        pin: str,
        client_id: str,
    ) -> TokenState:
        """Refresh by performing a new TOTP login (Dhan doesn't support refresh tokens).

        This is the same as ``login()`` — Dhan's TOTP flow always generates a fresh token.
        """
        return self.login(totp_secret, pin, client_id)


__all__ = ["DhanTotpClient", "DhanTotpError", "TotpRateLimitError"]

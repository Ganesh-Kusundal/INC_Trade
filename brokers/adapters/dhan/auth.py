"""Dhan auth — token management with state tracking.

Handles TOTP-based token generation, validity tracking, and refresh.
Integrates with TokenState for expiry awareness.
"""

from __future__ import annotations

import logging
import socket
from datetime import datetime, timezone
from typing import Any

import requests

from brokers.domain.exceptions import AuthenticationError, TokenRateLimitError
from brokers.infrastructure.storage.token_store import (
    TokenSource,
    TokenState,
    compute_token_expiry,
)
from brokers.infrastructure.totp_cooldown import TOTPCooldown, TotpRateLimitError

logger = logging.getLogger(__name__)


def _prefer_ipv4() -> None:
    """Patch socket to prefer IPv4 connections.

    Workaround for auth.dhan.co IPv6 connectivity issues where Python's
    requests library hangs on IPv6 connections while curl works fine with IPv4.
    """
    if not hasattr(socket, "_dhan_ipv4_patched"):
        original_getaddrinfo = socket.getaddrinfo

        def getaddrinfo_ipv4(*args: Any, **kwargs: Any) -> Any:
            results = original_getaddrinfo(*args, **kwargs)
            ipv4 = [r for r in results if r[0] == socket.AF_INET]
            return ipv4 if ipv4 else results

        socket.getaddrinfo = getaddrinfo_ipv4
        setattr(socket, "_dhan_ipv4_patched", True)



class DhanAuth:
    """Dhan authentication with token state tracking.

    Args:
        access_token: Pre-configured access token (skips TOTP generation).
        client_id: Dhan client ID.
        pin: Trading PIN for TOTP login.
        totp_secret: TOTP secret for token generation.
        token_lifetime_seconds: Token TTL for expiry calculation.
        token_store: Optional store to load/save token state.
    """

    def __init__(
        self,
        access_token: str | None = None,
        client_id: str | None = None,
        pin: str | None = None,
        totp_secret: str | None = None,
        token_lifetime_seconds: int = 86400,
        token_store: Any | None = None,
        totp_cooldown: TOTPCooldown | None = None,
    ):
        self._client_id = client_id or ""
        self._pin = pin
        self._totp_secret = totp_secret
        self._access_token = ""
        self._token_lifetime_seconds = token_lifetime_seconds
        self._state: TokenState | None = None
        self._token_store = token_store
        self._totp_cooldown = totp_cooldown or TOTPCooldown.for_broker("dhan")

        if access_token:
            # Use provided token
            self._access_token = access_token
        elif token_store is not None:
            # Try to load from store first
            try:
                state = token_store.load()
                if state and state.is_valid():
                    self._access_token = state.access_token
                    self._state = state
                    logger.info("token_loaded_from_store")
                elif pin and totp_secret:
                    # Store invalid, generate new token
                    self._access_token = self.generate_token()
            except Exception as exc:
                logger.warning("token_store_load_failed", extra={"error": str(exc)})
                if pin and totp_secret:
                    self._access_token = self.generate_token()
        elif pin and totp_secret:
            # No store, generate token
            self._access_token = self.generate_token()

        if self._access_token and not self._state:
            self._state = TokenState(
                access_token=self._access_token,
                source=TokenSource.TOTP if self._totp_secret else TokenSource.STATIC,
                issued_at=datetime.now(timezone.utc),
                expires_at=compute_token_expiry(token_lifetime_seconds),
            )

    @property
    def state(self) -> TokenState | None:
        """Current token state with validity metadata."""
        return self._state

    def get_token(self) -> str:
        """Return the current access token."""
        return self._access_token

    def is_valid(self) -> bool:
        """Check if current token is valid (non-empty and not expired)."""
        if self._state is not None:
            return self._state.is_valid()
        return bool(self._access_token)

    def is_authenticated(self) -> bool:
        """Check if authenticated (token exists)."""
        return bool(self._access_token)

    def generate_token(self) -> str:
        """Generate a fresh access token via TOTP.

        Returns:
            The new access token string.

        Raises:
            TokenRateLimitError: If Dhan's rate limit is hit.
            AuthenticationError: If token generation fails.
        """
        if not self._pin or not self._totp_secret:
            raise AuthenticationError(
                "pin and totp_secret are required to generate token"
            )

        try:
            self._totp_cooldown.check_allowed()
        except TotpRateLimitError as exc:
            raise TokenRateLimitError(str(exc)) from exc

        self._totp_cooldown.record_attempt()
        _prefer_ipv4()

        import pyotp
        from urllib.parse import urlencode

        from brokers.adapters.dhan.config import ENDPOINTS

        totp_code = pyotp.TOTP(self._totp_secret).now()
        params = {"dhanClientId": self._client_id, "pin": self._pin, "totp": totp_code}
        url = f"{ENDPOINTS['generate_token']}?{urlencode(params)}"

        try:
            resp = requests.post(url, timeout=15)  # Intentional: TOTP token generation uses raw requests to avoid DhanHttpClient's rate limiter for this one-shot endpoint
        except requests.RequestException as exc:
            raise AuthenticationError(
                f"Token generation request failed: {exc}"
            ) from exc

        try:
            body = resp.json()
        except Exception:
            body = {}

        message = body.get("message", "")
        status = body.get("status", "")

        if "once every 2 minutes" in message:
            self._totp_cooldown.record_rate_limited()
            raise TokenRateLimitError(f"Dhan token rate limit: {message}")

        if status == "error":
            raise AuthenticationError(
                f"Token generation failed: {message or 'unknown'}"
            )

        if resp.status_code != 200:
            body_text = resp.text
            if "once every" in body_text.lower() or "rate limit" in body_text.lower():
                self._totp_cooldown.record_rate_limited()
                raise TokenRateLimitError(f"Dhan token rate limit: {body_text}")
            raise AuthenticationError(
                f"Token generation failed: HTTP {resp.status_code}"
            )

        data = body.get("data", body)
        token = data.get("accessToken") or data.get("access_token") or ""
        if not token:
            raise AuthenticationError(
                f"Token generation failed: no token in response: {body}"
            )

        now = datetime.now(timezone.utc)
        self._state = TokenState(
            access_token=token,
            source=TokenSource.TOTP,
            issued_at=now,
            expires_at=compute_token_expiry(self._token_lifetime_seconds),
        )
        self._access_token = token
        self._totp_cooldown.record_success()
        logger.info("dhan_token_generated", extra={"client_id": self._client_id})
        return token

    def refresh_token(self) -> str:
        """Refresh the access token via TOTP regeneration.

        Returns:
            The new (or existing if refresh not possible) access token.
        """
        if self._pin and self._totp_secret:
            try:
                self._access_token = self.generate_token()
                logger.info("dhan_token_regenerated_successfully")
            except TokenRateLimitError as exc:
                logger.warning(
                    "dhan_token_refresh_rate_limited", extra={"error": str(exc)}
                )
            except AuthenticationError as exc:
                logger.error(
                    "dhan_token_regeneration_failed", extra={"error": str(exc)}
                )
        else:
            logger.warning("dhan_token_refresh_not_supported_without_totp_credentials")
        return self._access_token

    def acquire(self) -> TokenState | None:
        """Acquire a fresh token, returning the full state.

        Returns:
            TokenState if successful, None otherwise.
        """
        try:
            self.generate_token()
            return self._state
        except (TokenRateLimitError, AuthenticationError) as exc:
            logger.error("dhan_token_acquire_failed", extra={"error": str(exc)})
            return None

    def force_refresh(self) -> TokenState | None:
        """Force a token refresh regardless of current validity.

        Returns:
            TokenState if successful, None otherwise.
        """
        return self.acquire()

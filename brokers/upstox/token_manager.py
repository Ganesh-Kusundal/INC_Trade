"""Upstox token manager — manages the full Upstox token lifecycle.

Supports multiple authentication modes:
  - STATIC: Pre-obtained access token from env
  - TOTP: Automated login via mobile + pin + totp
  - OAUTH: OAuth PKCE flow (manual browser step)

The manager bootstraps from the best available source and proactively
refreshes before expiry. Thread-safe with a dedicated refresh lock.

Usage::

    from brokers.upstox.token_manager import UpstoxTokenManager
    from brokers.common.auth.credential_resolver import CredentialResolver

    creds = CredentialResolver.for_upstox()
    manager = UpstoxTokenManager(creds)
    manager.bootstrap()
    token = manager.access_token  # Always valid
"""

from __future__ import annotations

import logging
import threading
from typing import Callable

from brokers.common.auth.credential_resolver import UpstoxCredentials
from brokers.common.auth.token_manager import (
    AuthManager,
    JsonTokenStateStore,
    TokenSource,
    TokenState,
)
from brokers.upstox.totp_client import UpstoxTotpClient

logger = logging.getLogger(__name__)


class UpstoxTokenManager:
    """Manages Upstox token lifecycle with TOTP and static token support.

    Wraps an AuthManager with Upstox-specific bootstrap and refresh logic.

    Bootstrap order:
    1. Static token from credentials (if provided)
    2. Persisted token from JSON store (if still valid)
    3. TOTP login (if totp_secret, pin, mobile are available)

    Refresh strategy:
    - If TOTP credentials are available: perform a new TOTP login
    - Otherwise: raise (no refresh possible — user must re-authenticate)
    """

    def __init__(
        self,
        credentials: UpstoxCredentials,
        *,
        token_store_path: str = ".cache/upstox/token_state.json",
        refresh_buffer_minutes: float = 30,
    ) -> None:
        self._creds = credentials
        self._refresh_buffer_seconds = refresh_buffer_minutes * 60

        # Create auth callbacks
        on_acquire: Callable[[], TokenState] | None = None
        on_refresh: Callable[[TokenState], TokenState] | None = None

        if credentials.has_totp:
            totp_client = UpstoxTotpClient(api_key=credentials.api_key)

            def _totp_acquire() -> TokenState:
                return totp_client.login(
                    credentials.totp_secret,
                    credentials.pin,
                    credentials.mobile,
                )

            def _totp_refresh(old: TokenState) -> TokenState:
                return totp_client.refresh(
                    credentials.totp_secret,
                    credentials.pin,
                    credentials.mobile,
                )

            on_acquire = _totp_acquire
            on_refresh = _totp_refresh

        self._auth = AuthManager(
            on_acquire=on_acquire,
            on_refresh=on_refresh,
            store=JsonTokenStateStore(token_store_path),
            refresh_buffer_seconds=self._refresh_buffer_seconds,
            broker_name="upstox",
        )

        self._lock = threading.RLock()

    # ── Public API ───────────────────────────────────────────────────────

    def bootstrap(self) -> TokenState:
        """Bootstrap the token from the best available source.

        Tries static token → persisted token → TOTP login.
        """
        with self._lock:
            # 1. If we already have a valid token, use it
            state = self._auth.state
            if state is not None and state.is_valid:
                logger.debug("upstox_token_already_valid")
                return state

            # 2. If we have a static token from credentials, inject it into AuthManager
            if self._creds.access_token:
                static_state = TokenState(
                    access_token=self._creds.access_token,
                    source=TokenSource.STATIC,
                    broker_id=self._creds.client_id,
                )
                self._auth.set_state(static_state)
                logger.info("upstox_bootstrap_static_token")
                return static_state

            # 3. Acquire via TOTP/OAuth
            return self._auth.acquire()

    def ensure_valid(self) -> TokenState:
        """Ensure the token is valid, acquiring or refreshing if needed."""
        return self._auth.ensure_valid()

    def ensure_fresh(self) -> TokenState:
        """Ensure the token is valid and not approaching expiry."""
        return self._auth.ensure_fresh()

    @property
    def access_token(self) -> str:
        """Current access token string."""
        return self._auth.access_token

    @property
    def bearer_token(self) -> str:
        """Bearer token string for HTTP Authorization header."""
        return f"Bearer {self._auth.access_token}"

    @property
    def state(self) -> TokenState | None:
        """Current token state."""
        return self._auth.state

    @property
    def is_valid(self) -> bool:
        """Whether the current token is valid."""
        return self._auth.is_valid

    @property
    def refresh_count(self) -> int:
        return self._auth.refresh_count

    @property
    def error_count(self) -> int:
        return self._auth.error_count

    def register_token_receiver(self, callback: Callable[[str], None]) -> Callable[[str], None]:
        """Register a callback invoked when a new token is obtained."""
        return self._auth.register_token_receiver(callback)

    def unregister_token_receiver(self, callback: Callable[[str], None]) -> None:
        """Remove a previously registered token receiver."""
        self._auth.unregister_token_receiver(callback)

    def revoke(self) -> None:
        """Revoke the current token."""
        self._auth.revoke()


__all__ = ["UpstoxTokenManager"]

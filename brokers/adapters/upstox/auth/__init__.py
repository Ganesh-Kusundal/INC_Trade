"""Upstox auth package — full token lifecycle management.

Re-exports the public auth surface for the Upstox adapter.
"""

from __future__ import annotations

import logging
from typing import Any

from brokers.adapters.upstox.auth.exceptions import UpstoxApiError, UpstoxAuthError
from brokers.adapters.upstox.auth.holders import (
    ThreadSafeTokenHolder,
    TokenSnapshot,
    UpstoxAnalyticsTokenHolder,
    UpstoxExtendedTokenHolder,
    UpstoxStaticTokenHolder,
    UpstoxTokenHolder,
)
from brokers.adapters.upstox.auth.json_token_store import JsonTokenStateStore
from brokers.adapters.upstox.auth.oauth_client import TokenResponse, UpstoxOAuthClient
from brokers.adapters.upstox.auth.pkce import PkcePair, UpstoxPkceUtil
from brokers.adapters.upstox.auth.token_expiry import UpstoxTokenExpiry
from brokers.adapters.upstox.auth.token_manager import UpstoxTokenManager
from brokers.adapters.upstox.auth.totp_client import UpstoxTotpClient
from brokers.adapters.upstox.auth.redirect_server import UpstoxRedirectServer
from brokers.adapters.upstox.auth.totp_scheduler import TotpRefreshScheduler

logger = logging.getLogger(__name__)


class UpstoxAuth:
    """Simple auth facade for backward compatibility with the gateway.

    Wraps UpstoxTokenManager with the AuthPort interface.
    """

    def __init__(
        self,
        access_token: str = "",
        client_id: str = "",
        client_secret: str = "",
        refresh_token: str = "",
        mobile: str = "",
        pin: str = "",
        totp_secret: str = "",
        auth_mode: str = "STATIC",
        environment: str = "LIVE",
        token_state_file: Any = None,
        refresh_buffer_minutes: int = 30,
        redirect_uri: str = "",
    ) -> None:

        class _Settings:
            pass

        s = _Settings()
        s.client_id = client_id
        s.client_secret = client_secret
        s.access_token = access_token
        s.refresh_token = refresh_token
        s.mobile = mobile
        s.pin = pin
        s.totp_secret = totp_secret
        s.auth_mode = auth_mode.upper()
        s.environment = environment.upper()
        s.analytics_only = False
        s.extended_token = ""
        s.analytics_token = ""
        s.redirect_uri = redirect_uri or "http://localhost:18080"
        s.token_state_file = token_state_file
        s.refresh_buffer_minutes = refresh_buffer_minutes
        s.is_sandbox = s.environment == "SANDBOX"
        s.is_static = s.auth_mode == "STATIC"
        s.is_oauth = s.auth_mode == "OAUTH"
        s.is_totp = s.auth_mode == "TOTP"
        s.is_extended = s.auth_mode == "EXTENDED"
        s.is_interactive = s.auth_mode == "INTERACTIVE"
        s.is_webhook = s.auth_mode == "WEBHOOK"
        if s.is_sandbox:
            s.base_v2 = "https://sandbox-api.upstox.com"
            s.base_hft = "https://sandbox-api-hft.upstox.com"
        else:
            s.base_v2 = "https://api.upstox.com"
            s.base_hft = "https://api-hft.upstox.com"

        self._settings = s
        self._manager = UpstoxTokenManager(s)
        self._token_change_callbacks: list = []

    def get_token(self) -> str:
        return self._manager.bearer_token()

    def refresh_token(self) -> str:
        result = self._manager.force_refresh()
        return result.access_token if result else self._manager.current_token() or ""

    def is_authenticated(self) -> bool:
        token = self._manager.current_token()
        return bool(token) and token != "placeholder-no-token"

    def acquire(self) -> str | None:
        try:
            state = self._manager.bootstrap()
            return state.access_token
        except Exception as exc:
            logger.warning("Upstox auth acquire failed: %s", exc)
            return None

    def force_refresh(self) -> str | None:
        try:
            result = self._manager.force_refresh()
            token = result.access_token if result else None
            if token:
                for cb in self._token_change_callbacks:
                    try:
                        cb(token)
                    except Exception:
                        pass
            return token
        except Exception as exc:
            logger.warning("Upstox force_refresh failed: %s", exc)
            return None

    def expires_at(self):
        exp_ms = self._manager._effective_expiry_ms()
        if exp_ms <= 0:
            return None
        from datetime import datetime, timezone

        return datetime.fromtimestamp(exp_ms / 1000, tz=timezone.utc)

    def on_token_change(self, callback) -> None:
        self._token_change_callbacks.append(callback)

    @property
    def manager(self) -> UpstoxTokenManager:
        return self._manager


__all__ = [
    "JsonTokenStateStore",
    "PkcePair",
    "ThreadSafeTokenHolder",
    "TokenResponse",
    "TokenSnapshot",
    "UpstoxAnalyticsTokenHolder",
    "UpstoxApiError",
    "UpstoxAuth",
    "UpstoxAuthError",
    "UpstoxExtendedTokenHolder",
    "UpstoxOAuthClient",
    "UpstoxPkceUtil",
    "UpstoxRedirectServer",
    "UpstoxStaticTokenHolder",
    "UpstoxTokenExpiry",
    "UpstoxTokenHolder",
    "UpstoxTokenManager",
    "UpstoxTotpClient",
    "TotpRefreshScheduler",
]

"""Upstox auth package — full token lifecycle management.

Re-exports the public auth surface for the Upstox adapter.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC
from typing import Any

from brokers_core.infrastructure.storage.token_store import JsonTokenStateStore

from brokers_core.adapters.upstox.auth.config import (
    UpstoxConnectionSettings,
    UpstoxSettingsLoader,
)
from brokers_core.adapters.upstox.auth.exceptions import UpstoxApiError, UpstoxAuthError
from brokers_core.adapters.upstox.auth.holders import (
    ThreadSafeTokenHolder,
    TokenSnapshot,
    UpstoxAnalyticsTokenHolder,
    UpstoxExtendedTokenHolder,
    UpstoxStaticTokenHolder,
    UpstoxTokenHolder,
)
from brokers_core.adapters.upstox.auth.oauth_client import TokenResponse, UpstoxOAuthClient
from brokers_core.adapters.upstox.auth.pkce import PkcePair, UpstoxPkceUtil
from brokers_core.adapters.upstox.auth.redirect_server import UpstoxRedirectServer
from brokers_core.adapters.upstox.auth.token_expiry import UpstoxTokenExpiry
from brokers_core.adapters.upstox.auth.token_manager import UpstoxTokenManager
from brokers_core.adapters.upstox.auth.totp_client import UpstoxTotpClient
from brokers_core.adapters.upstox.auth.totp_scheduler import TotpRefreshScheduler

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
        analytics_only: bool = False,
        settings: UpstoxConnectionSettings | None = None,
    ) -> None:
        if settings is not None:
            s = settings
        else:
            s = UpstoxConnectionSettings(
                client_id=client_id or "default",
                client_secret=client_secret,
                access_token=access_token,
                refresh_token=refresh_token,
                mobile=mobile,
                pin=pin,
                totp_secret=totp_secret,
                auth_mode=auth_mode.upper(),
                environment=environment.upper(),
                analytics_only=analytics_only,
                redirect_uri=redirect_uri or "http://localhost:18080",
                token_state_file=token_state_file,
                refresh_buffer_minutes=refresh_buffer_minutes,
            )

        self._settings = s
        self._manager = UpstoxTokenManager(s)
        self._token_change_callbacks: list[Callable[[str], None]] = []

    def get_token(self) -> str:
        return self._manager.bearer_token()

    def try_refresh_on_401(self) -> bool:
        return self._manager.try_refresh_on_401()

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

    def expires_at(self) -> Any:
        exp_ms = self._manager._effective_expiry_ms()
        if exp_ms <= 0:
            return None
        from datetime import datetime, timezone

        return datetime.fromtimestamp(exp_ms / 1000, tz=UTC)

    @property
    def analytics_only(self) -> bool:
        return bool(getattr(self._settings, "analytics_only", False))

    @property
    def settings(self) -> UpstoxConnectionSettings:
        return self._settings

    def on_token_change(self, callback: Callable[[str], None]) -> None:
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
    "TotpRefreshScheduler",
    "UpstoxAnalyticsTokenHolder",
    "UpstoxApiError",
    "UpstoxAuth",
    "UpstoxAuthError",
    "UpstoxConnectionSettings",
    "UpstoxExtendedTokenHolder",
    "UpstoxOAuthClient",
    "UpstoxPkceUtil",
    "UpstoxRedirectServer",
    "UpstoxSettingsLoader",
    "UpstoxStaticTokenHolder",
    "UpstoxTokenExpiry",
    "UpstoxTokenHolder",
    "UpstoxTokenManager",
    "UpstoxTotpClient",
]

"""Authentication framework — reusable token lifecycle management.

Providers implement broker-specific auth logic.
This framework manages the lifecycle.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Optional

from tradex.core.errors import AuthenticationError, ErrorContext, SessionExpiredError
from tradex.core.token import TokenInfo  # noqa: F401 — re-exported for backward compat


@dataclass
class SessionState:
    """Current session state."""

    authenticated: bool = False
    token: Optional[TokenInfo] = None
    client_id: str = ""
    connected_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    refresh_count: int = 0
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.authenticated and self.token is not None and not self.token.is_expired


class AuthManager:
    """Reusable authentication lifecycle manager.

    Handles:
    - Token generation
    - Token refresh
    - Expiry detection
    - Automatic refresh before expiry
    - Session persistence
    """

    def __init__(
        self,
        auto_refresh: bool = True,
        refresh_threshold_seconds: int = 300,
    ) -> None:
        self._auto_refresh = auto_refresh
        self._refresh_threshold = refresh_threshold_seconds
        self._state = SessionState()
        self._refresh_lock = asyncio.Lock()
        self._on_token_refreshed: list[Callable[..., Coroutine[Any, Any, None]]] = []
        self._on_session_expired: list[Callable[..., Coroutine[Any, Any, None]]] = []

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def is_authenticated(self) -> bool:
        return self._state.is_valid

    @property
    def access_token(self) -> str:
        if self._state.token:
            return self._state.token.access_token
        return ""

    def on_token_refreshed(self, callback: Callable[..., Coroutine[Any, Any, None]]) -> None:
        """Register a callback for token refresh events."""
        self._on_token_refreshed.append(callback)

    def on_session_expired(self, callback: Callable[..., Coroutine[Any, Any, None]]) -> None:
        """Register a callback for session expiry events."""
        self._on_session_expired.append(callback)

    async def set_token(self, token: TokenInfo) -> None:
        """Store a new token."""
        self._state.token = token
        self._state.authenticated = True
        self._state.connected_at = datetime.now(timezone.utc)
        self._state.error = None

    async def save_session(self, broker: str = "", store: Optional[Any] = None) -> None:
        """Persist the current session to disk.

        Args:
            broker: Broker name for the storage key.
            store: A TokenStore instance. If None, no-op.
        """
        if store is None or self._state.token is None:
            return
        from tradex.core.storage import SessionSnapshot

        snapshot = SessionSnapshot.from_token_info(
            broker=broker,
            client_id=self._state.client_id,
            token=self._state.token,
        )
        await store.save(snapshot)

    async def load_session(self, broker: str = "", store: Optional[Any] = None) -> bool:
        """Restore a session from disk.

        Args:
            broker: Broker name for the storage key.
            store: A TokenStore instance. If None, no-op.

        Returns:
            True if a valid session was restored.
        """
        if store is None:
            return False
        snapshot = await store.load(broker, self._state.client_id)
        if snapshot is None:
            return False
        if not store.is_valid(snapshot):
            return False
        self._state.token = snapshot.to_token_info()
        self._state.authenticated = True
        self._state.client_id = snapshot.client_id
        return True

    async def invalidate(self, reason: str = "") -> None:
        """Mark the session as invalid."""
        self._state.authenticated = False
        self._state.error = reason
        for cb in self._on_session_expired:
            try:
                await cb()
            except Exception:
                pass

    async def ensure_valid(
        self, refresh_fn: Optional[Callable[..., Coroutine[Any, Any, TokenInfo]]] = None
    ) -> str:
        """Ensure we have a valid token, refreshing if needed.

        Returns the current access token.

        Raises:
            SessionExpiredError: If token is expired and refresh fails.
        """
        if self._state.token and not self._state.token.is_expired:
            # Check if needs proactive refresh
            if self._auto_refresh and self._state.token.needs_refresh and refresh_fn:
                await self._do_refresh(refresh_fn)
            return self._state.token.access_token

        # Token is expired or missing
        if refresh_fn:
            return await self._do_refresh(refresh_fn)

        raise SessionExpiredError(
            "No valid token and no refresh function available",
            code="TOKEN_EXPIRED",
        )

    async def _do_refresh(self, refresh_fn: Callable[..., Coroutine[Any, Any, TokenInfo]]) -> str:
        """Perform token refresh with locking."""
        async with self._refresh_lock:
            # Double-check after acquiring lock
            if self._state.token and not self._state.token.needs_refresh:
                return self._state.token.access_token

            try:
                new_token = await refresh_fn()
                await self.set_token(new_token)
                self._state.refresh_count += 1

                for cb in self._on_token_refreshed:
                    try:
                        await cb()
                    except Exception:
                        pass

                return new_token.access_token
            except Exception as e:
                await self.invalidate(str(e))
                if hasattr(e, 'code') and e.code in ('DH-904', '805'):
                    raise AuthenticationError(
                        f'Token refresh rate limit exceeded: {e}',
                        code='DH-904',
                        context=ErrorContext(retryable=True),
                    )
                elif hasattr(e, 'code') and e.code in ('DH-901', 'DH-902', 'DH-903'):
                    raise AuthenticationError(
                        f'Token refresh authentication failed: {e}',
                        code='DH-903',
                    )
                else:
                    raise AuthenticationError(
                        f'Token refresh failed: {e}',
                        code='DH-908',
                        context=ErrorContext(retryable=True),
                    ) from e

"""Auth manager — orchestrates token acquire, refresh, validation, and revocation.

Split from ``token_manager.py`` for maintainability.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from typing import Callable

from brokers.common.auth.token_state import (
    TokenState,
    TokenStateStore,
)
from brokers.common.logging_helpers import log_error, log_info

logger = logging.getLogger(__name__)


class AuthManager:
    """Manages the full token lifecycle: acquire, validate, refresh, revoke.

    Broker-specific auth modules create an AuthManager with:
      - ``on_acquire``: callback to obtain a fresh token (TOTP login, OAuth, etc.)
      - ``on_refresh``: callback to refresh an existing token
      - ``store``: persistent storage for the token state

    Usage::

        manager = AuthManager(
            on_acquire=lambda: dhan_totp_login(secret, pin, client_id),
            on_refresh=lambda old: dhan_refresh(old),
            store=JsonTokenStateStore("~/.dhan_token.json"),
        )
        manager.ensure_valid()
        token = manager.access_token
    """

    def __init__(
        self,
        *,
        on_acquire: Callable[[], TokenState] | None = None,
        on_refresh: Callable[[TokenState], TokenState] | None = None,
        store: TokenStateStore | None = None,
        refresh_buffer_seconds: float = 300,
        broker_name: str = "",
    ) -> None:
        self._on_acquire = on_acquire
        self._on_refresh = on_refresh
        self._store = store
        self._refresh_buffer = refresh_buffer_seconds
        self._broker_name = broker_name

        self._lock = threading.RLock()
        # Single-flight refresh coordination: only one thread performs a refresh
        # (acquire/refresh) at a time; all other callers wait on this Condition
        # and then reuse the resulting state instead of re-running the refresh.
        self._refresh_cond = threading.Condition(self._lock)
        self._refreshing = False  # True while a thread owns the single-flight refresh
        self._state: TokenState | None = None
        self._receivers: list[Callable[[str], None]] = []
        self._refresh_count = 0
        self._error_count = 0

        # Try loading from store on init
        if self._store is not None:
            loaded = self._store.load()
            if loaded is not None and loaded.access_token:
                self._state = loaded

    # ── Public API ───────────────────────────────────────────────────────

    @property
    def access_token(self) -> str:
        """Current access token. Raises if none available."""
        with self._lock:
            if self._state is None or not self._state.access_token:
                raise RuntimeError("No valid token — call acquire() or ensure_valid() first")
            return self._state.access_token

    @property
    def state(self) -> TokenState | None:
        """Current token state (or None if not acquired)."""
        with self._lock:
            return self._state

    @property
    def is_valid(self) -> bool:
        """Whether the current token is valid."""
        with self._lock:
            return self._state is not None and self._state.is_valid

    @property
    def refresh_count(self) -> int:
        return self._refresh_count

    @property
    def error_count(self) -> int:
        return self._error_count

    def acquire(self) -> TokenState:
        """Acquire a fresh token via the on_acquire callback.

        Raises RuntimeError if no on_acquire callback is set.
        Uses a single-flight refresh slot so concurrent callers wait for an
        in-progress acquire and then reuse its result.
        """
        if self._on_acquire is None:
            raise RuntimeError("No on_acquire callback configured")
        if not self._begin_refresh():
            return self._await_refresh(retry=self.acquire)
        try:
            return self._do_acquire()
        finally:
            self._end_refresh()

    def _do_acquire(self) -> TokenState:
        """Perform the actual on_acquire work (no single-flight handling)."""
        with self._lock:
            if self._state is not None and self._state.is_valid:
                return self._state
        try:
            new_state = self._on_acquire()
        except Exception as exc:
            with self._lock:
                self._error_count += 1
            log_error("token_acquire_failed", broker=self._broker_name, error=str(exc))
            raise
        with self._lock:
            self._set_state(new_state)
            self._refresh_count += 1
        log_info(
            "token_acquired",
            broker=self._broker_name,
            source=new_state.source.value,
            expires_at=new_state.expires_at.isoformat() if new_state.expires_at else None,
        )
        return new_state

    def ensure_valid(self) -> TokenState:
        """Ensure the current token is valid, acquiring if necessary.

        If the token is missing or expired, calls ``acquire()``.
        Does NOT proactively refresh — use ``ensure_fresh()`` for that.
        """
        with self._lock:
            if self._state is not None and self._state.is_valid:
                return self._state
        # Release lock before acquire (acquire takes the lock itself)
        return self.acquire()

    def ensure_fresh(self) -> TokenState:
        """Ensure the token is valid AND not approaching expiry.

        If ``refresh_recommended()`` is True, calls ``refresh()``.
        If no token at all, calls ``acquire()``.
        Uses a single-flight refresh slot so concurrent callers wait for an
        in-progress refresh and then reuse its result.
        """
        with self._lock:
            state = self._state
            if state is not None and state.is_valid:
                if not state.refresh_recommended(self._refresh_buffer):
                    return state  # Token is valid and fresh
                if self._on_refresh is None:
                    return state  # Can't refresh — return valid token as-is

        if not self._begin_refresh():
            return self._await_refresh(retry=self.ensure_fresh)

        try:
            # Only the single-flight owner reaches here.
            with self._lock:
                state = self._state
                if state is not None and state.is_valid:
                    if not state.refresh_recommended(self._refresh_buffer):
                        return state
                    if self._on_refresh is None:
                        return state

            # Perform refresh
            if self._on_refresh is not None:
                with self._lock:
                    current = self._state
                if current is not None and current.is_valid:
                    try:
                        new_state = self._on_refresh(current)
                        with self._lock:
                            self._set_state(new_state)
                            self._refresh_count += 1
                        log_info(
                            "token_refreshed",
                            broker=self._broker_name,
                            source=new_state.source.value,
                        )
                        return new_state
                    except Exception as exc:
                        with self._lock:
                            self._error_count += 1
                        log_error("token_refresh_failed", broker=self._broker_name, error=str(exc))
                        # Fall through to acquire

            # No valid token or refresh failed — acquire a fresh one
            return self._do_acquire()
        finally:
            self._end_refresh()

    def refresh(self) -> TokenState:
        """Refresh the token via the on_refresh callback.

        Falls back to ``acquire()`` if no on_refresh callback is set.
        """
        if self._on_refresh is None:
            return self.acquire()

        with self._lock:
            current = self._state
            if current is None:
                # No state to refresh — acquire instead
                return self.acquire()

        # Call on_refresh outside the lock to avoid deadlock
        try:
            new_state = self._on_refresh(current)
            with self._lock:
                self._set_state(new_state)
                self._refresh_count += 1
            log_info(
                "token_refreshed",
                broker=self._broker_name,
                source=new_state.source.value,
            )
            return new_state
        except Exception as exc:
            self._error_count += 1
            log_error("token_refresh_failed", broker=self._broker_name, error=str(exc))
            raise

    def set_state(self, state: TokenState) -> None:
        """Directly set the token state, bypassing acquire/refresh.

        Used for bootstrap from a static token or external auth flow.
        Persists to store and notifies receivers.
        """
        with self._lock:
            self._set_state(state)
        log_info("token_state_set", broker=self._broker_name, source=state.source.value)

    def revoke(self) -> None:
        """Revoke the current token and clear state."""
        with self._lock:
            self._state = None
            if self._store is not None:
                self._store.clear()
            log_info("token_revoked", broker=self._broker_name)

    def register_token_receiver(self, callback: Callable[[str], None]) -> Callable[[str], None]:
        """Register a callback invoked when a new token is set.

        Returns the callback (for use with context managers / deregistration patterns).
        """
        with self._lock:
            self._receivers.append(callback)
        return callback

    def unregister_token_receiver(self, callback: Callable[[str], None]) -> None:
        """Remove a previously registered token receiver."""
        with self._lock:
            with contextlib.suppress(ValueError):
                self._receivers.remove(callback)

    # ── Internal ─────────────────────────────────────────────────────────

    def _begin_refresh(self) -> bool:
        """Claim the single-flight refresh slot.

        Returns True if this thread is the single owner and must perform the
        refresh; False if another thread already owns it (the caller should then
        wait via ``_await_refresh`` and reuse the result).
        """
        with self._refresh_cond:
            if self._refreshing:
                return False
            self._refreshing = True
            return True

    def _end_refresh(self) -> None:
        """Release the single-flight refresh slot and wake all waiters."""
        with self._refresh_cond:
            self._refreshing = False
            self._refresh_cond.notify_all()

    def _await_refresh(self, *, retry: Callable[[], TokenState]) -> TokenState:
        """Wait for an in-progress refresh to complete, then return fresh state.

        After the owner finishes, re-check the existing state. If a refresh
        actually happened, the resulting state is returned without re-running
        the refresh. If the owner failed (no valid state produced), this thread
        retries to take ownership itself.
        """
        with self._refresh_cond:
            while self._refreshing:
                self._refresh_cond.wait()
            state = self._state
            if state is not None and state.is_valid:
                return state
        # Owner failed to produce a valid token — try to take ownership.
        if self._begin_refresh():
            try:
                return retry()
            finally:
                self._end_refresh()
        return self._await_refresh(retry=retry)

    def _set_state(self, new_state: TokenState) -> None:
        """Set new token state, persist, and notify receivers."""
        self._state = new_state
        if self._store is not None:
            with contextlib.suppress(Exception):
                self._store.save(new_state)
        # Notify receivers (failures don't interrupt)
        for receiver in list(self._receivers):
            with contextlib.suppress(Exception):
                receiver(new_state.access_token)


__all__ = ["AuthManager"]

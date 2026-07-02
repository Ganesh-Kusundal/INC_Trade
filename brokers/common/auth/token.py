"""Authentication module — inspired by Trade_J's auth architecture.

Patterns replicated from Trade_J:
- ``TokenSource``: enum categorizing token origins (STATIC, TOTP, OAUTH, INTERACTIVE)
- ``TokenState``: immutable token snapshot with expiry/refresh logic
- ``TokenStateStore``: abstract persistent storage interface
- ``AuthManager``: token lifecycle management (acquire, validate, refresh, revoke)
- ``TotpGenerator``: TOTP code generation for Dhan authentication
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import hmac
import json
import logging
import os
import struct
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from brokers.common.auth.jwt_expiry import JwtExpiry
from domain.constants import (
    TOKEN_CLOCK_SKEW_SECONDS,
    TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS,
)


class TokenSource(str, Enum):
    """Origin/category of an authentication token.

    Maps to Trade_J's TokenSource enum.
    """

    STATIC = "STATIC"  # Pre-configured, no refresh
    TOTP = "TOTP"  # Time-based One-Time Password
    OAUTH = "OAUTH"  # Authorization Code Grant with PKCE
    INTERACTIVE = "INTERACTIVE"  # Interactive login flow


@dataclass
class TokenState:
    """Immutable snapshot of token data.

    Maps to Trade_J's TokenState record.
    """

    access_token: str = ""
    refresh_token: str | None = None
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    source: TokenSource = TokenSource.STATIC

    # Clock-skew tolerance (see core.constants.TOKEN_CLOCK_SKEW_SECONDS)
    _CLOCK_SKEW_SECONDS: float = TOKEN_CLOCK_SKEW_SECONDS

    def is_valid(self) -> bool:
        """Check if the token is currently valid (with clock skew).

        Static tokens (no ``expires_at``) with a non-empty access token
        are considered valid since they never expire.
        """
        if not self.access_token:
            return False
        # Static tokens with no expiry are always valid
        if self.expires_at is None:
            return True
        return self.remaining_seconds() > -self._CLOCK_SKEW_SECONDS

    def remaining_seconds(self) -> float:
        """Seconds until token expires (negative = expired)."""
        if not self.expires_at:
            return 0.0
        # Use naive datetime for consistency — tests and callers create
        # naive datetimes with datetime.now()
        now = datetime.now()
        return (self.expires_at - now).total_seconds()

    def refresh_recommended(
        self, buffer_seconds: float = TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS
    ) -> bool:
        """Check if token should be refreshed within the given buffer.

        Args:
            buffer_seconds: How far before expiry to recommend refresh (default 5 min).

        Returns:
            True if refresh is recommended.
        """
        remaining = self.remaining_seconds()
        # Safety: don't proactively refresh short-lived tokens whose
        # entire lifespan is shorter than the buffer (matching Trade_J logic)
        total_lifetime = 0.0
        if self.issued_at and self.expires_at:
            total_lifetime = (self.expires_at - self.issued_at).total_seconds()
        if 0 < total_lifetime < buffer_seconds:
            return remaining < 10.0  # only when nearly expired
        return 0 < remaining < buffer_seconds


class TokenStateStore(ABC):
    """Abstract persistent storage for TokenState.

    Maps to Trade_J's TokenStateStore interface.
    """

    @abstractmethod
    def load(self) -> TokenState | None:
        """Load the persisted token state, or None if none exists."""
        ...

    @abstractmethod
    def save(self, state: TokenState | None) -> None:
        """Persist a token state. Passing None clears the store."""
        ...


class EnvTokenStateStore(TokenStateStore):
    """Loads token state from environment variables.

    Maps to Trade_J's EnvTokenStateStore.
    Variables: TRADEJ_TOKEN_ACCESS, TRADEJ_TOKEN_REFRESH, etc.
    """

    _PREFIX = "TRADEJ_TOKEN"

    def __init__(self, prefix: str = _PREFIX):
        self._prefix = prefix
        self._cache: TokenState | None = None

    def load(self) -> TokenState | None:
        if self._cache:
            return self._cache
        access = os.environ.get(f"{self._prefix}_ACCESS")
        if not access:
            return None
        refresh = os.environ.get(f"{self._prefix}_REFRESH")
        expires_str = os.environ.get(f"{self._prefix}_EXPIRES_AT")
        expires_at = None
        if expires_str:
            try:
                expires_at = datetime.fromisoformat(expires_str)
            except ValueError:
                expires_at = None
        state = TokenState(
            access_token=access,
            refresh_token=refresh,
            expires_at=expires_at,
            source=TokenSource.STATIC,
        )
        self._cache = state
        return state

    def save(self, state: TokenState | None) -> None:
        self._cache = state


class JsonTokenStateStore(TokenStateStore):
    """Persists TokenState as JSON on disk.

    Maps to Trade_J's persistent file-based store pattern.
    """

    def __init__(self, path: Path):
        self._path = path

    def load(self) -> TokenState | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text())
            expires_at = None
            if data.get("expires_at"):
                expires_at = datetime.fromisoformat(data["expires_at"])
            issued_at = None
            if data.get("issued_at"):
                issued_at = datetime.fromisoformat(data["issued_at"])
            return TokenState(
                access_token=data.get("access_token", ""),
                refresh_token=data.get("refresh_token"),
                issued_at=issued_at,
                expires_at=expires_at,
                source=TokenSource(data.get("source", "STATIC")),
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def save(self, state: TokenState | None) -> None:
        if state is None:
            if self._path.exists():
                self._path.unlink()
            return
        data: dict[str, Any] = {
            "access_token": state.access_token,
            "refresh_token": state.refresh_token,
            "source": state.source.value,
        }
        if state.issued_at:
            data["issued_at"] = state.issued_at.isoformat()
        if state.expires_at:
            data["expires_at"] = state.expires_at.isoformat()

        # Write with secure file permissions (owner read/write only)
        self._path.write_text(json.dumps(data, indent=2))
        with contextlib.suppress(OSError):
            os.chmod(self._path, 0o600)
            # Best effort - file already written securely by default umask


class TotpGenerator:
    """Generate TOTP codes for Dhan authentication.

    Maps to Trade_J's DhanTotpGenerator. Uses HMAC-SHA1 with 30-second
    time steps and 6-digit output, matching Dhan's requirements.
    """

    _BASE32_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    _DIGITS = 6
    _TIME_STEP_SECONDS = 30

    def current_code(self, shared_secret: str) -> str:
        """Generate the current TOTP code from a Base32 shared secret.

        Args:
            shared_secret: Base32-encoded secret from Dhan.

        Returns:
            6-digit TOTP code as string.
        """
        return self.code_at(shared_secret, time.time())

    def code_at(self, shared_secret: str, timestamp: float) -> str:
        """Generate TOTP code at a specific timestamp.

        Args:
            shared_secret: Base32-encoded secret.
            timestamp: Unix timestamp.

        Returns:
            6-digit TOTP code as string.
        """
        if not shared_secret or not shared_secret.strip():
            raise ValueError("Dhan TOTP secret is blank")

        secret_bytes = self._decode_base32(shared_secret)
        counter = int(timestamp) // self._TIME_STEP_SECONDS

        # HMAC-SHA1
        counter_bytes = struct.pack(">Q", counter)
        hmac_hash = hmac.new(secret_bytes, counter_bytes, hashlib.sha1).digest()

        # Dynamic truncation
        offset = hmac_hash[-1] & 0x0F
        truncated = (
            ((hmac_hash[offset] & 0x7F) << 24)
            | ((hmac_hash[offset + 1] & 0xFF) << 16)
            | ((hmac_hash[offset + 2] & 0xFF) << 8)
            | (hmac_hash[offset + 3] & 0xFF)
        )

        otp = truncated % (10**self._DIGITS)
        return f"{otp:0{self._DIGITS}d}"

    def _decode_base32(self, value: str) -> bytes:
        """Decode Base32-encoded string to bytes.

        Normalizes input (strips spaces, dashes, uppercases) and handles
        both standard and padded Base32.
        """
        normalized = value.replace(" ", "").replace("-", "").strip().upper()
        if not normalized:
            raise ValueError("Dhan TOTP secret is blank")

        # Add padding if needed
        padding_needed = (8 - len(normalized) % 8) % 8
        normalized += "=" * padding_needed

        try:
            return base64.b32decode(normalized)
        except Exception as e:
            raise ValueError(f"Invalid Base32 in Dhan TOTP secret: {e}") from e


class AuthManager:
    """Manages token lifecycle for a broker connection.

    Maps to Trade_J's TokenLifecycleService.

    Usage::
        store = JsonTokenStateStore(Path("token.json"))
        auth = AuthManager(
            client_id="my_id",
            token_store=store,
            token_source=TokenSource.STATIC,
            on_acquire=lambda: acquire_token_sdk(),
        )
        token = auth.acquire()
        if auth.ensure_valid():
            # token is fresh
    """

    def __init__(
        self,
        client_id: str,
        token_store: TokenStateStore | None = None,
        token_source: TokenSource = TokenSource.STATIC,
        on_acquire: Callable[[], str] | None = None,
        on_refresh: Callable[[], str] | None = None,
        token_lifetime_seconds: float | None = None,
    ):
        self.client_id = client_id
        self._store = token_store
        self._source = token_source
        self._on_acquire = on_acquire
        self._on_refresh = on_refresh
        self._token_lifetime_seconds = token_lifetime_seconds
        self._state: TokenState | None = None
        self._expiry_callbacks: list[Callable[[], None]] = []
        self._refresh_callbacks: list[Callable[[], None]] = []

    # ── State ────────────────────────────────────────────────────

    @property
    def state(self) -> TokenState | None:
        return self._state

    @property
    def is_authenticated(self) -> bool:
        return self._state is not None and self._state.is_valid()

    # ── Lifecycle (maps to Trade_J's TokenLifecycleService) ──────

    def acquire(self) -> TokenState | None:
        """Acquire a token — from store first, then via callback.

        Maps to TokenLifecycleService.acquireToken().
        """
        # Try store first
        if self._store:
            stored = self._store.load()
            if stored and stored.is_valid():
                self._state = stored
                self._notify_refresh()
                return stored

        # Try acquire callback
        if self._on_acquire:
            token_str = self._on_acquire()
            if token_str:
                self._state = self._make_token_state(token_str)
                if self._store:
                    self._store.save(self._state)
                self._notify_refresh()
                return self._state

        return None

    def ensure_valid(
        self, buffer_seconds: float = TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS
    ) -> bool:
        """Ensure the current token is present and not expired.

        Does **not** proactively refresh tokens that are still valid.
        Use :meth:`ensure_fresh` for OAuth-style proactive refresh.
        """
        del buffer_seconds  # validity-only; buffer ignored
        if self._state and self._state.is_valid():
            return True
        result = self.acquire()
        return result is not None and result.is_valid()

    def ensure_fresh(
        self, buffer_seconds: float = TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS
    ) -> bool:
        """Ensure token is valid; proactively refresh when within *buffer* of expiry."""
        if self._state and self._state.is_valid():
            if not self._state.refresh_recommended(buffer_seconds):
                return True
            return self._do_refresh()
        result = self.acquire()
        return result is not None

    def force_refresh(self) -> TokenState | None:
        """Force token regeneration via ``on_refresh``, bypassing persisted store.

        Used when the broker rejects a locally-valid token (401/DH-906) and
        ``acquire()`` would reload the same stale value from disk.
        """
        if self._do_refresh():
            return self._state
        return None

    def revoke(self) -> None:
        """Revoke the current token and clear the store.

        Maps to TokenLifecycleService.revoke().
        """
        self._state = None
        if self._store:
            self._store.save(None)
        self._notify_expiry()

    # ── Callbacks (maps to Trade_J's onExpiry / onRefresh) ───────

    def on_expiry(self, callback: Callable[[], None]) -> None:
        """Register a callback for when the token expires."""
        self._expiry_callbacks.append(callback)

    def on_refresh(self, callback: Callable[[], None]) -> None:
        """Register a callback for when the token is refreshed."""
        self._refresh_callbacks.append(callback)

    # ── Internal ─────────────────────────────────────────────────

    def _make_token_state(self, token_str: str) -> TokenState:
        """Create a TokenState with JWT-derived expiry when available."""
        issued_at = datetime.now()
        expires_at = JwtExpiry.parse_expiry_datetime(token_str)
        if expires_at is None and self._token_lifetime_seconds is not None:
            expires_at = issued_at + timedelta(seconds=self._token_lifetime_seconds)
        return TokenState(
            access_token=token_str,
            source=self._source,
            issued_at=issued_at,
            expires_at=expires_at,
        )

    def _do_refresh(self) -> bool:
        if not self._on_refresh:
            return False
        try:
            token_str = self._on_refresh()
            if token_str:
                self._state = self._make_token_state(token_str)
                if self._store:
                    self._store.save(self._state)
                self._notify_refresh()
                return True
        except Exception as exc:
            logger = logging.getLogger(__name__)
            logger.warning(
                "token_refresh_failed", extra={"client_id": self.client_id, "error": str(exc)}
            )
            return False
        return False

    def _set_token(self, token_str: str, source: TokenSource = TokenSource.STATIC) -> None:
        """Set the token state directly (used by brokers on init).

        Properly initializes the state through the public lifecycle
        rather than bypassing it via direct ``_state`` assignment.
        """
        self._state = self._make_token_state(token_str)
        if self._store:
            self._store.save(self._state)
        self._notify_refresh()

    def _notify_refresh(self) -> None:
        self._notify_callbacks(self._refresh_callbacks)

    def _notify_expiry(self) -> None:
        self._notify_callbacks(self._expiry_callbacks)

    @staticmethod
    def _notify_callbacks(callbacks: list[Callable[[], None]]) -> None:
        for callback in callbacks:
            with contextlib.suppress(Exception):
                callback()

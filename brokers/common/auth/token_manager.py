"""Common auth — token state, token manager, and TOTP generator.

This module provides the shared authentication infrastructure:
  - TokenState: immutable snapshot of an access token + metadata
  - AuthManager: lifecycle management (acquire, refresh, validate, revoke)
  - TotpGenerator: RFC 6238 TOTP code generation (no external dependency)

Broker-specific auth modules extend these with their own login flows.
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
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


def _log_warning(msg: str, **extra: object) -> None:
    """Safe structured warning that won't crash if the logger uses StructuredLogger."""
    try:
        logger.warning(msg, extra=extra)
    except TypeError:
        logger.warning(f"{msg} {extra}")


def _log_info(msg: str, **extra: object) -> None:
    """Safe structured info that won't crash if the logger uses StructuredLogger."""
    try:
        logger.info(msg, extra=extra)
    except TypeError:
        logger.info(f"{msg} {extra}")


def _log_error(msg: str, **extra: object) -> None:
    """Safe structured error that won't crash if the logger uses StructuredLogger."""
    try:
        logger.error(msg, extra=extra)
    except TypeError:
        logger.error(f"{msg} {extra}")


def _log_debug(msg: str, **extra: object) -> None:
    """Safe structured debug that won't crash if the logger uses StructuredLogger."""
    try:
        logger.debug(msg, extra=extra)
    except TypeError:
        logger.debug(f"{msg} {extra}")


# ── Token source enum ──────────────────────────────────────────────────────


class TokenSource(str, Enum):
    """How the token was obtained."""
    STATIC = "static"       # Loaded from env/config
    TOTP = "totp"           # Generated via TOTP login
    OAUTH = "oauth"         # Obtained via OAuth flow
    INTERACTIVE = "interactive"  # Manual login
    REFRESH = "refresh"     # Refreshed from a refresh token


# ── Token state ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TokenState:
    """Immutable snapshot of an authentication token.

    Carries the access token, optional refresh token, expiry, and provenance.
    """

    access_token: str
    refresh_token: str = ""
    expires_at: datetime | None = None
    source: TokenSource = TokenSource.STATIC
    token_type: str = "bearer"
    scope: str = ""
    broker_id: str = ""

    @property
    def is_valid(self) -> bool:
        """Whether the token is still valid (not expired)."""
        if self.expires_at is None:
            return True  # No expiry known — assume valid
        return datetime.now(timezone.utc) < self.expires_at

    @property
    def remaining_seconds(self) -> float:
        """Seconds until expiry. Returns float('inf') if no expiry."""
        if self.expires_at is None:
            return float("inf")
        delta = self.expires_at - datetime.now(timezone.utc)
        return max(0.0, delta.total_seconds())

    def refresh_recommended(self, buffer_seconds: float = 300) -> bool:
        """Whether a proactive refresh is recommended (within buffer of expiry)."""
        if self.expires_at is None:
            return False
        return self.remaining_seconds <= buffer_seconds

    @classmethod
    def from_expiry_seconds(
        cls,
        access_token: str,
        expires_in_seconds: int,
        *,
        refresh_token: str = "",
        source: TokenSource = TokenSource.STATIC,
        broker_id: str = "",
    ) -> TokenState:
        """Create a TokenState from an ``expires_in`` seconds value (common API format)."""
        expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
        return cls(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expiry,
            source=source,
            broker_id=broker_id,
        )

    def to_dict(self) -> dict:
        """Serialize to a JSON-safe dict for persistence."""
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "source": self.source.value,
            "token_type": self.token_type,
            "scope": self.scope,
            "broker_id": self.broker_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TokenState:
        """Deserialize from a dict (e.g. loaded from JSON file)."""
        expires_at_str = data.get("expires_at")
        expires_at = None
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
            except (ValueError, TypeError):
                pass
        source_str = data.get("source", "static")
        try:
            source = TokenSource(source_str)
        except ValueError:
            source = TokenSource.STATIC
        return cls(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token", ""),
            expires_at=expires_at,
            source=source,
            token_type=data.get("token_type", "bearer"),
            scope=data.get("scope", ""),
            broker_id=data.get("broker_id", ""),
        )


# ── Token state store protocol ─────────────────────────────────────────────


@runtime_checkable
class TokenStateStore(Protocol):
    """Protocol for persistent token storage."""

    def load(self) -> TokenState | None:
        """Load token state from storage. Returns None if not found."""
        ...

    def save(self, state: TokenState) -> None:
        """Persist token state to storage."""
        ...

    def clear(self) -> None:
        """Remove stored token state."""
        ...


class EnvTokenStateStore:
    """Load tokens from environment variables.

    Reads ``{PREFIX}_ACCESS_TOKEN``, ``{PREFIX}_REFRESH_TOKEN``,
    ``{PREFIX}_TOKEN_EXPIRY`` from the environment.
    """

    def __init__(self, prefix: str = "DHAN") -> None:
        self._prefix = prefix

    def load(self) -> TokenState | None:
        access = os.environ.get(f"{self._prefix}_ACCESS_TOKEN", "")
        if not access:
            return None
        refresh = os.environ.get(f"{self._prefix}_REFRESH_TOKEN", "")
        expiry_str = os.environ.get(f"{self._prefix}_TOKEN_EXPIRY", "")
        expires_at = None
        if expiry_str:
            try:
                expires_at = datetime.fromisoformat(expiry_str)
            except ValueError:
                pass
        return TokenState(
            access_token=access,
            refresh_token=refresh,
            expires_at=expires_at,
            source=TokenSource.STATIC,
            broker_id=os.environ.get(f"{self._prefix}_CLIENT_ID", ""),
        )

    def save(self, state: TokenState) -> None:
        """Env store is read-only — saving is a no-op."""
        _log_debug("EnvTokenStateStore.save is a no-op (read-only)")

    def clear(self) -> None:
        """Env store is read-only — clearing is a no-op."""
        _log_debug("EnvTokenStateStore.clear is a no-op (read-only)")


class JsonTokenStateStore:
    """Persist token state to a JSON file with secure permissions.

    File permissions are set to 0o600 (owner read/write only) on save.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def load(self) -> TokenState | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return TokenState.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            _log_warning("token_state_load_failed", error=str(exc), path=str(self._path))
            return None

    def save(self, state: TokenState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(state.to_dict(), indent=2),
            encoding="utf-8",
        )
        # Set secure file permissions (owner read/write only)
        with contextlib.suppress(OSError, PermissionError):
            os.chmod(self._path, 0o600)

    def clear(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._path.unlink()


# ── TOTP generator (RFC 6238) ──────────────────────────────────────────────


class TotpGenerator:
    """RFC 6238 TOTP generator — no external dependencies.

    Generates 6-digit codes using HMAC-SHA1 with a 30-second time step.
    Compatible with Google Authenticator, Authy, etc.
    """

    _TIME_STEP = 30  # seconds
    _DIGITS = 6
    _ALGORITHM = hashlib.sha1

    @staticmethod
    def _decode_base32(secret: str) -> bytes:
        """Decode a base32-encoded secret.

        Normalizes the secret by stripping spaces/dashes, uppercasing,
        and padding to a multiple of 8 characters.
        """
        cleaned = secret.replace(" ", "").replace("-", "").upper()
        # Add padding if needed
        padding = (8 - len(cleaned) % 8) % 8
        cleaned = cleaned + "=" * padding
        return base64.b32decode(cleaned)

    @classmethod
    def code_at(cls, secret: str, timestamp: float | None = None) -> str:
        """Generate a TOTP code for the given timestamp.

        Args:
            secret: Base32-encoded shared secret.
            timestamp: Unix timestamp (defaults to now).

        Returns:
            6-digit TOTP code as a string.
        """
        if timestamp is None:
            timestamp = time.time()

        key = cls._decode_base32(secret)
        counter = int(timestamp // cls._TIME_STEP)

        # Pack counter as 8-byte big-endian
        msg = struct.pack(">Q", counter)

        # HMAC-SHA1
        h = hmac.new(key, msg, cls._ALGORITHM).digest()

        # Dynamic truncation (RFC 4226)
        offset = h[-1] & 0x0F
        truncated = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF

        code = truncated % (10 ** cls._DIGITS)
        return str(code).zfill(cls._DIGITS)

    @classmethod
    def code_now(cls, secret: str) -> str:
        """Generate the current TOTP code."""
        return cls.code_at(secret, time.time())

    @classmethod
    def seconds_remaining(cls, timestamp: float | None = None) -> int:
        """Seconds remaining in the current TOTP window."""
        if timestamp is None:
            timestamp = time.time()
        elapsed = timestamp % cls._TIME_STEP
        return cls._TIME_STEP - int(elapsed)


# ── TOTP cooldown guard ────────────────────────────────────────────────────


class TotpCooldownGuard:
    """Prevents TOTP generation rate-limiting by tracking last attempt time.

    Broker APIs (especially Dhan) enforce cooldown periods between TOTP-based
    login attempts. This guard persists the last attempt time to a JSON file
    so cooldowns survive process restarts.
    """

    def __init__(
        self,
        cooldown_seconds: int = 120,
        persist_path: str | Path | None = None,
    ) -> None:
        self._cooldown_seconds = cooldown_seconds
        self._persist_path = Path(persist_path) if persist_path else None
        self._lock = threading.Lock()
        self._last_attempt: float = 0.0

        # Load persisted state
        if self._persist_path and self._persist_path.exists():
            try:
                data = json.loads(self._persist_path.read_text(encoding="utf-8"))
                self._last_attempt = float(data.get("last_attempt", 0))
            except (json.JSONDecodeError, ValueError, TypeError):
                pass

    def can_generate(self) -> bool:
        """Whether a new TOTP login attempt is allowed (cooldown has passed)."""
        with self._lock:
            if self._last_attempt == 0:
                return True
            elapsed = time.time() - self._last_attempt
            return elapsed >= self._cooldown_seconds

    def seconds_until_allowed(self) -> float:
        """Seconds until the next TOTP attempt is allowed."""
        with self._lock:
            if self._last_attempt == 0:
                return 0.0
            elapsed = time.time() - self._last_attempt
            remaining = self._cooldown_seconds - elapsed
            return max(0.0, remaining)

    def record_attempt(self) -> None:
        """Record that a TOTP login attempt was made."""
        with self._lock:
            self._last_attempt = time.time()
            if self._persist_path:
                self._persist_path.parent.mkdir(parents=True, exist_ok=True)
                self._persist_path.write_text(
                    json.dumps({"last_attempt": self._last_attempt}),
                    encoding="utf-8",
                )

    def reset(self) -> None:
        """Reset the cooldown (e.g. after a successful login)."""
        with self._lock:
            self._last_attempt = 0.0
            if self._persist_path and self._persist_path.exists():
                with contextlib.suppress(FileNotFoundError):
                    self._persist_path.unlink()


# ── Auth manager ───────────────────────────────────────────────────────────


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
        """
        if self._on_acquire is None:
            raise RuntimeError("No on_acquire callback configured")

        with self._lock:
            try:
                new_state = self._on_acquire()
                self._set_state(new_state)
                self._refresh_count += 1
                _log_info(
                    "token_acquired",
                    broker=self._broker_name,
                    source=new_state.source.value,
                    expires_at=new_state.expires_at.isoformat() if new_state.expires_at else None,
                )
                return new_state
            except Exception as exc:
                self._error_count += 1
                _log_error("token_acquire_failed", broker=self._broker_name, error=str(exc))
                raise

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
        """
        with self._lock:
            state = self._state
            if state is not None and state.is_valid:
                if not state.refresh_recommended(self._refresh_buffer):
                    return state  # Token is valid and fresh
                # Token is valid but stale — try to refresh
                if self._on_refresh is None:
                    return state  # Can't refresh — return valid token as-is
                # Fall through to refresh below

        # Refresh if we have a valid-but-stale token and a refresh callback
        with self._lock:
            if (
                self._state is not None
                and self._state.is_valid
                and self._on_refresh is not None
            ):
                return self.refresh()

        # No valid token (or expired) — acquire a fresh one
        return self.acquire()

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
            _log_info(
                "token_refreshed",
                broker=self._broker_name,
                source=new_state.source.value,
            )
            return new_state
        except Exception as exc:
            self._error_count += 1
            _log_error("token_refresh_failed", broker=self._broker_name, error=str(exc))
            raise

    def force_refresh(self) -> TokenState:
        """Force a refresh, bypassing the store (use when broker rejects token)."""
        return self.refresh()

    def set_state(self, state: TokenState) -> None:
        """Directly set the token state, bypassing acquire/refresh.

        Used for bootstrap from a static token or external auth flow.
        Persists to store and notifies receivers.
        """
        with self._lock:
            self._set_state(state)
        _log_info("token_state_set", broker=self._broker_name, source=state.source.value)

    def revoke(self) -> None:
        """Revoke the current token and clear state."""
        with self._lock:
            self._state = None
            if self._store is not None:
                self._store.clear()
            _log_info("token_revoked", broker=self._broker_name)

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


__all__ = [
    "AuthManager",
    "EnvTokenStateStore",
    "JsonTokenStateStore",
    "TokenSource",
    "TokenState",
    "TokenStateStore",
    "TotpCooldownGuard",
    "TotpGenerator",
]

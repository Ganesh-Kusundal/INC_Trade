"""Token state — immutable token snapshot, storage protocols, and implementations.

Split from ``token_manager.py`` for maintainability.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Protocol, runtime_checkable

from brokers.common.logging_helpers import log_debug, log_warning

logger = logging.getLogger(__name__)


def _parse_expires_at(value: str | None) -> datetime | None:
    """Parse an ISO timestamp, attaching UTC tzinfo if it is naive.

    JSON-serialized datetimes lose tzinfo, so they become naive. Comparing
    a naive datetime against an aware one (``datetime.now(timezone.utc)``)
    raises ``TypeError`` in Python 3, so we coerce naive values to UTC.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


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

    def _expiry(self) -> datetime | None:
        """Return ``expires_at`` coerced to UTC (naive values assumed UTC).

        JSON-serialized datetimes lose tzinfo and become naive; comparing a
        naive datetime against ``datetime.now(timezone.utc)`` raises
        ``TypeError`` in Python 3. Coercing here keeps ``is_valid`` and
        ``remaining_seconds`` safe even if a ``TokenState`` is built with a
        naive ``expires_at`` directly.
        """
        if self.expires_at is None:
            return None
        if self.expires_at.tzinfo is None:
            return self.expires_at.replace(tzinfo=timezone.utc)
        return self.expires_at

    @property
    def is_valid(self) -> bool:
        """Whether the token is still valid (not expired)."""
        expiry = self._expiry()
        if expiry is None:
            return True  # No expiry known — assume valid
        return datetime.now(timezone.utc) < expiry

    @property
    def remaining_seconds(self) -> float:
        """Seconds until expiry. Returns float('inf') if no expiry."""
        expiry = self._expiry()
        if expiry is None:
            return float("inf")
        delta = expiry - datetime.now(timezone.utc)
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
        expires_at = _parse_expires_at(data.get("expires_at"))
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
        expires_at = _parse_expires_at(os.environ.get(f"{self._prefix}_TOKEN_EXPIRY", ""))
        return TokenState(
            access_token=access,
            refresh_token=refresh,
            expires_at=expires_at,
            source=TokenSource.STATIC,
            broker_id=os.environ.get(f"{self._prefix}_CLIENT_ID", ""),
        )

    def save(self, state: TokenState) -> None:
        """Env store is read-only — saving is a no-op."""
        log_debug("EnvTokenStateStore.save is a no-op (read-only)")

    def clear(self) -> None:
        """Env store is read-only — clearing is a no-op."""
        log_debug("EnvTokenStateStore.clear is a no-op (read-only)")


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
            log_warning("token_state_load_failed", error=str(exc), path=str(self._path))
            return None

    def save(self, state: TokenState) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(state.to_dict(), indent=2)
        # Create the file with secure 0o600 permissions from the start so the
        # plaintext token is never exposed world/group-readable, even briefly.
        fd = os.open(
            self._path,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(data)
        except (OSError, PermissionError):
            # Best-effort tighten on failure; never leave it silently world-readable.
            with contextlib.suppress(OSError, PermissionError):
                os.chmod(self._path, 0o600)
            raise
        # Guarantee final mode is 0o600; a failure to tighten must be loud.
        try:
            os.chmod(self._path, 0o600)
        except OSError as exc:
            raise PermissionError(
                f"Failed to set secure permissions on token file {self._path}: {exc}"
            ) from exc

    def clear(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._path.unlink()


__all__ = [
    "EnvTokenStateStore",
    "JsonTokenStateStore",
    "TokenSource",
    "TokenState",
    "TokenStateStore",
]

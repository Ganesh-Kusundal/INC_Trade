"""Token persistence — atomic file writes and JSON state storage.

Provides durable token storage via:
- JsonTokenStateStore: JSON file-based token state persistence
- update_env_token: Atomic .env file updates with fcntl.flock
- TokenState: Token metadata (access_token, expires_at, source)
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TokenSource(str, Enum):
    """How the token was acquired."""

    STATIC = "STATIC"
    TOTP = "TOTP"
    OAUTH = "OAUTH"
    INTERACTIVE = "INTERACTIVE"


@dataclass
class TokenState:
    """Token metadata with validity tracking.

    Args:
        access_token: The access token string.
        refresh_token: Optional refresh token (not used by Dhan).
        issued_at: When the token was obtained.
        expires_at: When the token expires.
        source: How the token was acquired.
    """

    access_token: str = ""
    refresh_token: str | None = None
    issued_at: datetime | None = None
    expires_at: datetime | None = None
    source: TokenSource = TokenSource.STATIC

    _CLOCK_SKEW_SECONDS: float = field(default=30.0, init=False, repr=False)

    def is_valid(self) -> bool:
        """Check if token is non-empty and not expired."""
        if not self.access_token:
            return False
        if self.expires_at is None:
            return True
        return self.remaining_seconds() > -self._CLOCK_SKEW_SECONDS

    def remaining_seconds(self) -> float:
        """Seconds until expiry. Negative if expired."""
        if self.expires_at is None:
            return float("inf")
        if self.expires_at.tzinfo is not None:
            now = datetime.now(UTC)
        else:
            now = datetime.now()
        return (self.expires_at - now).total_seconds()

    def refresh_recommended(self, buffer_seconds: float = 300.0) -> bool:
        """Check if token should be refreshed proactively."""
        if self.expires_at is None:
            return False
        remaining = self.remaining_seconds()
        return 0 < remaining < buffer_seconds


class TokenStateStore:
    """Abstract base for token state persistence."""

    def load(self) -> TokenState | None:
        raise NotImplementedError

    def save(self, state: TokenState | None) -> None:
        raise NotImplementedError


class JsonTokenStateStore(TokenStateStore):
    """JSON file-based token state persistence.

    Implements the ``TokenStorePort`` protocol.

    Stores token state as JSON with atomic writes.
    File permissions are set to 0o600 (owner read/write only).

    Args:
        path: Path to the JSON file.
    """

    __implements__ = ("TokenStorePort",)

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def load(self) -> TokenState | None:
        """Load token state from JSON file. Returns None if missing or invalid."""
        if not self._path.exists():
            return None
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            return self._from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError, OSError) as exc:
            logger.debug("token_state_load_failed", extra={"error": str(exc)})
            return None

    def save(self, state: TokenState | None) -> None:
        """Save token state to JSON file. Deletes file if state is None."""
        if state is None:
            with contextlib.suppress(OSError):
                self._path.unlink()
            return

        self._path.parent.mkdir(parents=True, exist_ok=True)

        fd = None
        tmp_path = None
        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=self._path.parent,
                prefix=self._path.stem,
                suffix=".tmp",
            )
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._to_dict(state), f, indent=2)
            fd = None
            os.replace(tmp_path, self._path)
            tmp_path = None
        except OSError as exc:
            logger.warning("token_state_save_failed", extra={"error": str(exc)})
            raise
        finally:
            if fd is not None:
                with contextlib.suppress(OSError):
                    os.close(fd)
            if tmp_path is not None:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)

    def _from_dict(self, data: dict[str, Any]) -> TokenState:
        """Parse JSON dict into TokenState."""
        return TokenState(
            access_token=data.get("access_token", ""),
            refresh_token=data.get("refresh_token"),
            issued_at=self._parse_datetime(data.get("issued_at")),
            expires_at=self._parse_datetime(data.get("expires_at")),
            source=TokenSource(data.get("source", "STATIC")),
        )

    def _to_dict(self, state: TokenState) -> dict[str, Any]:
        """Convert TokenState to JSON-serializable dict."""
        result = asdict(state)
        result["issued_at"] = state.issued_at.isoformat() if state.issued_at else None
        result["expires_at"] = state.expires_at.isoformat() if state.expires_at else None
        result["source"] = state.source.value
        return result

    @staticmethod
    def _parse_datetime(value: str | None) -> datetime | None:
        """Parse ISO format datetime string."""
        if not value:
            return None
        return datetime.fromisoformat(value)


def update_env_token(
    env_path: Path,
    token: str,
    *,
    env_key: str = "DHAN_ACCESS_TOKEN",
) -> None:
    """Atomically update token in .env file.

    Uses fcntl.flock for exclusive access, writes to temp file,
    then atomically replaces the original. Falls back gracefully
    if the file is read-only.

    Args:
        env_path: Path to the .env file.
        token: New token value.
        env_key: Environment variable name (default: DHAN_ACCESS_TOKEN).
    """
    if not env_path.exists():
        logger.debug("env_file_missing", extra={"path": str(env_path)})
        return

    fd = None
    tmp_path = None
    try:
        fd = os.open(str(env_path), os.O_RDWR | os.O_CREAT, 0o600)
        try:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass

        with os.fdopen(fd, "r+", encoding="utf-8", closefd=False) as f:
            content = f.read()

        prefix = f"{env_key}="
        lines = content.splitlines(keepends=True)
        new_lines = []
        found = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith(prefix) and not found:
                new_lines.append(f"{prefix}{token}\n")
                found = True
            else:
                new_lines.append(line)

        if not found:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines[-1] += "\n"
            new_lines.append(f"{prefix}{token}\n")

        new_content = "".join(new_lines)

        tmp_fd = None
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=env_path.parent,
                prefix=env_path.stem,
                suffix=".tmp",
            )
            os.fchmod(tmp_fd, 0o600)
            with os.fdopen(tmp_fd, "w", encoding="utf-8", closefd=False) as f:
                f.write(new_content)
                f.flush()
                os.fsync(f.fileno())
            tmp_fd = None

            dir_fd = os.open(env_path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)

            os.replace(tmp_path, env_path)
            tmp_path = None
            logger.info("env_token_updated", extra={"key": env_key, "path": str(env_path)})

        except PermissionError:
            logger.warning("env_file_read_only", extra={"path": str(env_path)})
        finally:
            if tmp_fd is not None:
                with contextlib.suppress(OSError):
                    os.close(tmp_fd)

    except OSError as exc:
        logger.warning("env_token_update_failed", extra={"error": str(exc), "path": str(env_path)})
    finally:
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)
        if tmp_path is not None:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)


def compute_token_expiry(lifetime_seconds: int = 86400) -> datetime:
    """Compute token expiry aligned to Dhan's trading session boundary.

    Dhan tokens expire at the start of the next trading day (~06:00 IST /
    00:30 UTC). If the current time is before today's 00:30 UTC, the
    expiry is today's 00:30; otherwise tomorrow's.

    Args:
        lifetime_seconds: Fallback TTL if session boundary calculation fails.

    Returns:
        Datetime when the token expires (UTC).
    """
    now = datetime.now(UTC)
    try:
        session_end_today = now.replace(hour=0, minute=30, second=0, microsecond=0)
        if now < session_end_today:
            return session_end_today
        return session_end_today + timedelta(days=1)
    except (ValueError, TypeError, AttributeError) as exc:
        logger.warning("token_expiry_fallback", extra={"error": str(exc)})
        return now + timedelta(seconds=lifetime_seconds)

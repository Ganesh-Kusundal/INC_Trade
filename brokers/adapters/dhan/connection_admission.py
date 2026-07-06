"""Host-wide admission gate for a single Dhan WebSocket connection per account.

Dhan allows up to five concurrent WebSocket connections, but this codebase
enforces one connection per (client_id, connection_type) pair per host via
fcntl file locking and a shared cooldown file after HTTP 429.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows dev machines
    fcntl = None  # type: ignore[assignment]


def _sanitize_client_id(client_id: Any) -> str:
    """Sanitize client_id for use in file paths."""
    if not isinstance(client_id, str):
        return f"auto_{id(client_id)}"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", client_id.strip()) or "unknown"


def _default_state_dir() -> Path:
    """Get default state directory for lock/cooldown files."""
    env_dir = os.getenv("DHAN_TOKEN_STATE_DIR", "").strip()
    if env_dir:
        return Path(env_dir)
    return Path(__file__).resolve().parents[4] / "runtime"


def _parse_iso_utc(value: str) -> datetime | None:
    """Parse ISO UTC timestamp."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        return None


class ConnectionAdmission:
    """Non-blocking host lock + shared 429 cooldown for WS connections."""

    def __init__(
        self,
        client_id: str,
        state_dir: Path | None = None,
        connection_type: str = "market-feed",
    ) -> None:
        self._client_id = client_id
        self._connection_type = connection_type
        self._state_dir = (state_dir or _default_state_dir()).resolve()
        self._state_dir.mkdir(parents=True, exist_ok=True)
        safe_id = _sanitize_client_id(client_id)
        safe_type = _sanitize_client_id(connection_type)
        self._lock_path = self._state_dir / f"dhan-{safe_type}-{safe_id}.lock"
        self._cooldown_path = (
            self._state_dir / f"dhan-{safe_type}-{safe_id}.cooldown.json"
        )
        self._lock_file: Any | None = None
        self._lock_held = False
        self._blocked_by_lock = False
        self._consecutive_rate_limits = self._load_persisted_streak()

    @property
    def lock_held(self) -> bool:
        return self._lock_held

    @property
    def blocked_by_lock(self) -> bool:
        return self._blocked_by_lock

    def try_acquire(self) -> bool:
        """Attempt a non-blocking host-wide lock. Returns True when acquired."""
        if self._lock_held:
            return True
        if fcntl is None:
            logger.warning(
                "market_feed_admission_no_fcntl; allowing connect without host lock"
            )
            self._lock_held = True
            self._blocked_by_lock = False
            return True

        try:
            handle = self._lock_path.open("a+")
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self._blocked_by_lock = True
            with contextlib.suppress(Exception):
                handle.close()
            logger.warning(
                "market_feed_connection_lock_held",
                extra={
                    "client_id": self._client_id,
                    "connection_type": self._connection_type,
                    "lock_path": str(self._lock_path),
                },
            )
            return False
        except OSError as exc:
            self._blocked_by_lock = True
            logger.error(
                "market_feed_admission_lock_error",
                extra={
                    "client_id": self._client_id,
                    "connection_type": self._connection_type,
                    "error": str(exc),
                },
            )
            return False

        self._lock_file = handle
        self._lock_held = True
        self._blocked_by_lock = False
        logger.info(
            "market_feed_connection_lock_acquired",
            extra={
                "client_id": self._client_id,
                "connection_type": self._connection_type,
                "lock_path": str(self._lock_path),
            },
        )
        return True

    def release(self) -> None:
        """Release the host-wide lock if this process holds it."""
        if not self._lock_held:
            return
        if self._lock_file is not None and fcntl is not None:
            with contextlib.suppress(Exception):
                fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_UN)
            with contextlib.suppress(Exception):
                self._lock_file.close()
        self._lock_file = None
        self._lock_held = False
        self._blocked_by_lock = False
        logger.info(
            "market_feed_connection_lock_released",
            extra={
                "client_id": self._client_id,
                "connection_type": self._connection_type,
            },
        )

    def seconds_until_connect_allowed(self) -> float:
        """Return seconds to wait before next SDK handshake is allowed."""
        next_allowed = self.next_connect_allowed_at()
        if next_allowed is None:
            return 0.0
        remaining = (next_allowed - datetime.now(UTC)).total_seconds()
        return max(0.0, remaining)

    def next_connect_allowed_at(self) -> datetime | None:
        if not self._cooldown_path.exists():
            return None
        try:
            payload = json.loads(self._cooldown_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        raw = payload.get("next_allowed_at")
        if not isinstance(raw, str):
            return None
        return _parse_iso_utc(raw)

    def status(self) -> dict[str, Any]:
        next_allowed = self.next_connect_allowed_at()
        return {
            "connection_type": self._connection_type,
            "connection_lock_acquired": self._lock_held,
            "connection_blocked_by_lock": self._blocked_by_lock,
            "next_connect_allowed_at": (
                next_allowed.isoformat() if next_allowed is not None else None
            ),
            "seconds_until_connect_allowed": self.seconds_until_connect_allowed(),
            "consecutive_rate_limits": self._consecutive_rate_limits,
            "admission_lock_path": str(self._lock_path),
        }

    def record_rate_limit_cooldown(self) -> datetime:
        """Persist escalating cooldown after Dhan HTTP 429 on WS handshake."""
        base = float(os.getenv("DHAN_WS_429_COOLDOWN_SECONDS", "120"))
        ceiling = float(os.getenv("DHAN_WS_429_COOLDOWN_MAX_SECONDS", "900"))

        self._consecutive_rate_limits += 1
        multiplier = 2 ** (self._consecutive_rate_limits - 1)
        cooldown_seconds = min(base * multiplier, ceiling)

        next_dt = datetime.fromtimestamp(
            datetime.now(UTC).timestamp() + cooldown_seconds,
            tz=UTC,
        )
        payload = {
            "client_id": self._client_id,
            "connection_type": self._connection_type,
            "next_allowed_at": next_dt.isoformat(),
            "reason": "http_429",
            "cooldown_seconds": cooldown_seconds,
            "consecutive_rate_limits": self._consecutive_rate_limits,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        try:
            self._cooldown_path.write_text(
                json.dumps(payload, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("market_feed_cooldown_write_failed: %s", exc)

        logger.warning(
            "market_feed_rate_limit_cooldown_recorded",
            extra={
                "client_id": self._client_id,
                "connection_type": self._connection_type,
                "cooldown_seconds": cooldown_seconds,
                "consecutive_rate_limits": self._consecutive_rate_limits,
                "next_allowed_at": next_dt.isoformat(),
            },
        )
        return next_dt

    def clear_cooldown(self) -> None:
        self._consecutive_rate_limits = 0
        with contextlib.suppress(OSError):
            if self._cooldown_path.exists():
                self._cooldown_path.unlink()

    def _read_cooldown_payload(self) -> dict[str, Any] | None:
        if not self._cooldown_path.exists():
            return None
        try:
            payload = json.loads(self._cooldown_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def _penalty_window_seconds(self) -> float:
        return float(os.getenv("DHAN_WS_429_PENALTY_WINDOW_SECONDS", "3600"))

    def _streak_from_payload(self, payload: dict[str, Any]) -> int:
        recorded_at = (
            _parse_iso_utc(payload["recorded_at"])
            if isinstance(payload.get("recorded_at"), str)
            else None
        )
        if recorded_at is None:
            return 0
        age = (datetime.now(UTC) - recorded_at).total_seconds()
        if age > self._penalty_window_seconds():
            return 0
        streak = payload.get("consecutive_rate_limits")
        return int(streak) if isinstance(streak, int) and streak > 0 else 1

    def _load_persisted_streak(self) -> int:
        """Reload consecutive rate limit streak while penalty window is active."""
        payload = self._read_cooldown_payload()
        if payload is None:
            return 0
        return self._streak_from_payload(payload)


class NoopAdmission:
    """No-op admission gate for unit tests. Always permits connects."""

    @property
    def lock_held(self) -> bool:
        return True

    @property
    def blocked_by_lock(self) -> bool:
        return False

    def try_acquire(self) -> bool:
        return True

    def release(self) -> None:
        pass

    def seconds_until_connect_allowed(self) -> float:
        return 0.0

    def next_connect_allowed_at(self) -> None:
        return None

    def record_rate_limit_cooldown(self) -> datetime:
        return datetime.now(UTC)

    def clear_cooldown(self) -> None:
        pass

    def status(self) -> dict[str, Any]:
        return {
            "connection_type": "noop",
            "connection_lock_acquired": True,
            "connection_blocked_by_lock": False,
            "next_connect_allowed_at": None,
            "seconds_until_connect_allowed": 0.0,
            "consecutive_rate_limits": 0,
            "admission_lock_path": "(noop)",
        }

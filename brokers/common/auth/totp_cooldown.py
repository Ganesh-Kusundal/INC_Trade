"""Process-wide TOTP rate-limit guard.

Broker login APIs enforce their own OTP/TOTP lockouts.  This guard keeps
local processes from accidentally hammering those endpoints across restarts.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import ClassVar

from brokers.common.resilience.errors import TradeXV2Error

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN_SECONDS = 120.0
BROKER_COOLDOWN_SECONDS: dict[str, float] = {
    "dhan": 120.0,
    "upstox": 600.0,
}


class TotpRateLimitError(TradeXV2Error):
    """Raised when TOTP generation is blocked by broker or local cooldown."""


class TotpCooldownGuard:
    """Shared cooldown tracker for TOTP token generation attempts."""

    _lock: ClassVar[threading.Lock] = threading.Lock()
    _instances: ClassVar[dict[str, TotpCooldownGuard]] = {}

    def __init__(
        self,
        broker: str,
        cooldown_seconds: float | None = None,
        state_path: Path | None = None,
    ) -> None:
        self._broker = broker.lower()
        self._cooldown_seconds = (
            cooldown_seconds
            if cooldown_seconds is not None
            else BROKER_COOLDOWN_SECONDS.get(self._broker, DEFAULT_COOLDOWN_SECONDS)
        )
        self._state_path = (
            state_path
            or Path(__file__).resolve().parents[2]
            / "runtime"
            / f"{self._broker}-totp-cooldown.json"
        )
        self._last_attempt_at: float | None = None
        self._last_success_at: float | None = None
        self._load_state()

    @classmethod
    def for_broker(
        cls, broker: str, cooldown_seconds: float | None = None
    ) -> TotpCooldownGuard:
        key = broker.lower()
        with cls._lock:
            if key not in cls._instances:
                cls._instances[key] = cls(key, cooldown_seconds=cooldown_seconds)
            return cls._instances[key]

    def _load_state(self) -> None:
        if not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text())
            self._last_attempt_at = self._coerce_wall_clock(data.get("last_attempt_at"))
            self._last_success_at = self._coerce_wall_clock(data.get("last_success_at"))
        except Exception as exc:
            logger.debug("totp_cooldown_load_failed: %s", exc)

    @staticmethod
    def _coerce_wall_clock(value: object) -> float | None:
        """Return epoch seconds, ignoring old monotonic timestamps."""
        try:
            ts = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        # Older versions persisted time.monotonic(); those small values are
        # meaningless after process restart and should not extend lockouts.
        if ts < 1_000_000_000:
            return None
        return ts

    def _persist_state(self) -> None:
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "broker": self._broker,
                "last_attempt_at": self._last_attempt_at,
                "last_success_at": self._last_success_at,
            }
            self._state_path.write_text(json.dumps(payload, indent=2))
        except Exception as exc:
            logger.debug("totp_cooldown_persist_failed: %s", exc)

    def remaining_cooldown_seconds(self) -> float:
        """Seconds until another TOTP attempt is allowed."""
        if self._last_attempt_at is None:
            return 0.0
        elapsed = time.time() - self._last_attempt_at
        return max(0.0, self._cooldown_seconds - elapsed)

    def check_allowed(self) -> None:
        """Raise ``TotpRateLimitError`` if cooldown is active."""
        remaining = self.remaining_cooldown_seconds()
        if remaining > 0:
            raise TotpRateLimitError(
                f"{self._broker} TOTP cooldown active; retry in {remaining:.0f}s"
            )

    def record_attempt(self) -> None:
        with self._lock:
            self._last_attempt_at = time.time()
            self._persist_state()

    def record_success(self) -> None:
        with self._lock:
            now = time.time()
            self._last_attempt_at = now
            self._last_success_at = now
            self._persist_state()

    def record_rate_limited(self) -> None:
        """Record a broker-side rate limit — enforce full cooldown."""
        with self._lock:
            self._last_attempt_at = time.time()
            self._persist_state()

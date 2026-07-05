"""Process-wide TOTP rate-limit guard.

Broker login APIs enforce their own OTP/TOTP lockouts.  This guard keeps
local processes from accidentally hammering those endpoints across restarts.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import struct
import threading
import time
from pathlib import Path
from typing import ClassVar

from inc_trade.domain.exceptions import TradeXV2Error

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN_SECONDS = 120.0
BROKER_COOLDOWN_SECONDS: dict[str, float] = {
    "dhan": 120.0,
    "upstox": 600.0,
}


class TotpRateLimitError(TradeXV2Error):
    """Raised when TOTP generation is blocked by broker or local cooldown."""


class TOTPCooldown:
    """Shared cooldown tracker for TOTP token generation attempts.

    Provides RFC 6238 TOTP code generation (HMAC-SHA1, 6 digits, 30 s window)
    together with process-wide cooldown enforcement so that repeated login
    attempts do not trigger broker-side lockouts.
    """

    _lock: ClassVar[threading.Lock] = threading.Lock()
    _instances: ClassVar[dict[str, TOTPCooldown]] = {}

    def __init__(
        self,
        broker: str,
        totp_secret: str = "",
        cooldown_seconds: float | None = None,
        state_path: Path | None = None,
    ) -> None:
        self._broker = broker.lower()
        self._totp_secret = totp_secret
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

    # -- factory -------------------------------------------------------------

    @classmethod
    def for_broker(
        cls,
        broker: str,
        totp_secret: str = "",
        cooldown_seconds: float | None = None,
    ) -> TOTPCooldown:
        key = broker.lower()
        with cls._lock:
            if key not in cls._instances:
                cls._instances[key] = cls(
                    key, totp_secret=totp_secret, cooldown_seconds=cooldown_seconds
                )
            return cls._instances[key]

    # -- TOTP generation (RFC 6238) ------------------------------------------

    def current_code(self) -> str:
        """Generate the current 6-digit TOTP code (HMAC-SHA1, 30 s window)."""
        if not self._totp_secret:
            return ""
        counter = int(time.time()) // 30
        key = _base32_decode(self._totp_secret)
        msg = struct.pack(">Q", counter)
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        code_int = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
        return str(code_int % 10**6).zfill(6)

    # -- cooldown API --------------------------------------------------------

    def can_request(self) -> bool:
        """Return True if a TOTP request is allowed (cooldown has elapsed)."""
        return self.remaining_cooldown_seconds() <= 0

    def mark_requested(self) -> None:
        """Record that a TOTP request was made, starting the cooldown."""
        with self._lock:
            self._last_attempt_at = time.time()
            self._persist_state()

    def check_allowed(self) -> None:
        """Raise ``TotpRateLimitError`` if cooldown is active."""
        remaining = self.remaining_cooldown_seconds()
        if remaining > 0:
            raise TotpRateLimitError(
                f"{self._broker} TOTP cooldown active; retry in {remaining:.0f}s"
            )

    def record_attempt(self) -> None:
        """Alias for ``mark_requested`` — kept for backward compatibility."""
        self.mark_requested()

    def record_success(self) -> None:
        with self._lock:
            now = time.time()
            self._last_attempt_at = now
            self._last_success_at = now
            self._persist_state()

    def record_rate_limited(self) -> None:
        """Record a broker-side rate limit -- enforce full cooldown."""
        with self._lock:
            self._last_attempt_at = time.time()
            self._persist_state()

    def remaining_cooldown_seconds(self) -> float:
        """Seconds until another TOTP attempt is allowed."""
        if self._last_attempt_at is None:
            return 0.0
        elapsed = time.time() - self._last_attempt_at
        return max(0.0, self._cooldown_seconds - elapsed)

    # -- persistence ---------------------------------------------------------

    def _load_state(self) -> None:
        if not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text())
            self._last_attempt_at = self._coerce_wall_clock(
                data.get("last_attempt_at")
            )
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _base32_decode(secret: str) -> bytes:
    """Decode a base32-encoded TOTP secret, tolerating common variants."""
    import base64

    cleaned = secret.upper().replace(" ", "").replace("=", "")
    # Pad to multiple of 8
    remainder = len(cleaned) % 8
    if remainder:
        cleaned += "=" * (8 - remainder)
    return base64.b32decode(cleaned)

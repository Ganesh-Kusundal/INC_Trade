"""TOTP generator (RFC 6238) and cooldown guard.

Split from ``token_manager.py`` for maintainability.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import hashlib
import hmac
import json
import logging
import struct
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)


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
        # 1. Strip whitespace/hyphens and uppercase FIRST.
        cleaned = secret.replace(" ", "").replace("-", "").strip().upper()
        # 2. Then pad to a multiple of 8 with '='.
        padding = (8 - len(cleaned) % 8) % 8
        cleaned = cleaned + "=" * padding
        # 3. Then decode.
        try:
            return base64.b32decode(cleaned)
        except binascii.Error as exc:
            raise ValueError(
                f"Invalid TOTP secret: must be base32 (A-Z2-7), got: {secret!r}"
            ) from exc

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


__all__ = [
    "TotpCooldownGuard",
    "TotpGenerator",
]

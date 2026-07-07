"""MFA / TOTP support for brokers requiring multi-factor authentication.

Provides TOTP generation and verification for brokers that
require MFA during login or sensitive operations.
"""

from __future__ import annotations

import hashlib
import hmac
import struct
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class TOTPConfig:
    """TOTP configuration."""

    secret: str = ""
    interval: int = 30  # seconds
    digits: int = 6
    algorithm: str = "sha1"  # sha1, sha256, sha512


class TOTPGenerator:
    """Time-based One-Time Password generator.

    Implements RFC 6238 TOTP for MFA flows.

    Usage:
        totp = TOTPGenerator(secret="JBSWY3DPEHPK3PXP")
        code = totp.generate()
        is_valid = totp.verify("123456")
    """

    def __init__(self, config: TOTPConfig) -> None:
        self._config = config
        self._secret_bytes = self._decode_secret(config.secret)

    def generate(self, timestamp: Optional[float] = None) -> str:
        """Generate a TOTP code.

        Args:
            timestamp: Unix timestamp. Uses current time if None.

        Returns:
            TOTP code as a string (e.g., "123456").
        """
        ts = timestamp or time.time()
        counter = int(ts) // self._config.interval
        return self._generate_hotp(counter)

    def verify(self, code: str, window: int = 1) -> bool:
        """Verify a TOTP code.

        Checks current window and +/- window intervals to account
        for clock skew.

        Args:
            code: The TOTP code to verify.
            window: Number of intervals to check in each direction.

        Returns:
            True if the code is valid.
        """
        now = time.time()
        counter = int(now) // self._config.interval

        for offset in range(-window, window + 1):
            expected = self._generate_hotp(counter + offset)
            if hmac.compare_digest(code, expected):
                return True
        return False

    def time_remaining(self) -> int:
        """Seconds remaining before the current code expires."""
        now = time.time()
        return self._config.interval - (int(now) % self._config.interval)

    def _generate_hotp(self, counter: int) -> str:
        """Generate HOTP code for a given counter."""
        # Encode counter as 8-byte big-endian
        counter_bytes = struct.pack(">Q", counter)

        # Compute HMAC
        hash_name = {
            "sha1": hashlib.sha1,
            "sha256": hashlib.sha256,
            "sha512": hashlib.sha512,
        }.get(self._config.algorithm, hashlib.sha1)

        hmac_digest = hmac.new(self._secret_bytes, counter_bytes, hash_name).digest()

        # Dynamic truncation
        offset = hmac_digest[-1] & 0x0F
        code_int = struct.unpack(">I", hmac_digest[offset : offset + 4])[0] & 0x7FFFFFFF

        # Truncate to desired digits
        code = code_int % (10**self._config.digits)
        return str(code).zfill(self._config.digits)

    @staticmethod
    def _decode_secret(secret: str) -> bytes:
        """Decode base32-encoded secret to bytes."""
        import base64

        # Add padding if needed
        padding = 4 - len(secret) % 4
        if padding != 4:
            secret += "=" * padding
        return base64.b32decode(secret.upper())

    @classmethod
    def from_secret(cls, secret: str, digits: int = 6, interval: int = 30) -> TOTPGenerator:
        """Create a TOTP generator from a raw secret string."""
        return cls(TOTPConfig(secret=secret, digits=digits, interval=interval))

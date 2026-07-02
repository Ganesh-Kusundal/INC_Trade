"""Auth gate helpers for integration tests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass
class _TotpGate:
    """Represents whether TOTP-based auth is configured for live tests."""

    configured: bool = False

    def generate(self) -> str:
        return ""


def upstox_totp_gate() -> _TotpGate:
    """Return a TOTP gate indicating whether Upstox TOTP auth is configured."""
    has_client = bool(os.environ.get("UPSTOX_CLIENT_ID", "").strip())
    has_secret = bool(os.environ.get("UPSTOX_TOTP_SECRET", "").strip())
    return _TotpGate(configured=has_client and has_secret)

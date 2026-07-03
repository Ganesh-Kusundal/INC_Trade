"""Parse JWT ``exp`` claim without signature verification."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone


def parse_jwt_expiry(token: str | None) -> datetime | None:
    """Parse JWT exp claim and return as naive local datetime, or None on failure."""
    if not token:
        return None
    parts = token.split(".")
    if len(parts) < 2:
        return None
    try:
        payload_bytes = base64.urlsafe_b64decode(_pad(parts[1]))
        payload = json.loads(payload_bytes.decode("utf-8"))
        exp = payload.get("exp")
        if exp is None:
            return None
        return datetime.fromtimestamp(int(exp))
    except Exception:
        return None


def is_expired(token: str | None, clock_skew_ms: int = 0) -> bool:
    """Check whether *token* has expired (or will within *clock_skew_ms*)."""
    exp_ms = _parse_expiry_epoch_ms(token)
    if exp_ms < 0:
        return True
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    return now_ms >= (exp_ms - clock_skew_ms)


def seconds_until_expiry(token: str | None, clock_skew_s: int = 30) -> int:
    """Seconds until the token expires, or 0 if already expired."""
    exp_ms = _parse_expiry_epoch_ms(token)
    if exp_ms < 0:
        return 0
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    remaining_ms = exp_ms - now_ms
    remaining_s = max(0, remaining_ms // 1000 - clock_skew_s)
    return remaining_s


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parse_expiry_epoch_ms(jwt: str | None) -> int:
    """Return exp claim as epoch milliseconds, or -1 on any failure."""
    if not jwt:
        return -1
    parts = jwt.split(".")
    if len(parts) < 2:
        return -1
    try:
        payload_bytes = base64.urlsafe_b64decode(_pad(parts[1]))
        payload = json.loads(payload_bytes.decode("utf-8"))
        exp = payload.get("exp")
        if exp is None:
            return -1
        return int(exp) * 1000
    except Exception:
        return -1


def _pad(value: str) -> str:
    remainder = len(value) % 4
    if remainder == 0:
        return value
    return value + "=" * (4 - remainder)

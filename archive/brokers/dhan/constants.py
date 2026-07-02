"""Dhan broker-specific constants.

Constants governing Dhan WebSocket subscription limits, idempotency
cache configuration, and other broker-specific tuning parameters.

These were previously defined in ``domain/constants/__init__.py`` but
belong here because they are broker-specific implementation details,
not domain-level abstractions.
"""

from __future__ import annotations

# ── WebSocket subscription limits ──────────────────────────────────────────

#: Max instruments per Dhan depth-20 WebSocket subscription.
DHAN_DEPTH_20_MAX_INSTRUMENTS: int = 50

#: Max instruments per Dhan depth-200 WebSocket subscription.
DHAN_DEPTH_200_MAX_INSTRUMENTS: int = 1

# ── Idempotency ────────────────────────────────────────────────────────────

#: Dhan OrderIdempotencyCache max size.
DHAN_IDEMPOTENCY_MAX_SIZE: int = 1_000

#: Dhan OrderIdempotencyCache TTL (seconds).
DHAN_IDEMPOTENCY_TTL_SECONDS: int = 60 * 60  # 1h

__all__ = [
    "DHAN_DEPTH_20_MAX_INSTRUMENTS",
    "DHAN_DEPTH_200_MAX_INSTRUMENTS",
    "DHAN_IDEMPOTENCY_MAX_SIZE",
    "DHAN_IDEMPOTENCY_TTL_SECONDS",
]

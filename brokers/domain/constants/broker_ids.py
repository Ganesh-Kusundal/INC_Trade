"""Broker ID constants — canonical string values for broker identification.

Use these constants instead of raw string literals like ``"dhan"`` or
``"upstox"`` in adapter attributes, routing logic, and configuration.
This prevents typo-related bugs and enables refactoring of broker
identification to a single source of truth.

Usage::

    from brokers.domain.constants.broker_ids import DHAN_ID, UPSTOX_ID

    class DhanAdapter:
        broker_id: str = DHAN_ID
"""

from __future__ import annotations

#: Canonical broker identifier for Dhan.
DHAN_ID: str = "dhan"

#: Canonical broker identifier for Upstox.
UPSTOX_ID: str = "upstox"

#: Canonical broker identifier for Paper (simulated) trading.
PAPER_ID: str = "paper"

__all__ = [
    "DHAN_ID",
    "UPSTOX_ID",
    "PAPER_ID",
]

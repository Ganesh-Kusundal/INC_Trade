"""Broker identity types.

Canonical broker identifiers. Every broker adapter (Dhan, Upstox, Paper)
has a corresponding enum member. Use ``BrokerId`` (or ``BrokerSource``)
instead of raw string literals ``"dhan"``, ``"upstox"``, ``"paper"``
throughout the codebase.

Usage::

    from brokers.common.identity import BrokerId

    gw_id: BrokerId = BrokerId.DHAN
    if gw_id == BrokerId.UPSTOX:
        ...
"""

from __future__ import annotations

from brokers.common.api.spi import BrokerSource as BrokerSource

# Convenience alias — either name works.
BrokerId = BrokerSource

__all__ = [
    "BrokerId",
    "BrokerSource",
]

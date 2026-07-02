"""Canonical enums — the vocabulary of the trading domain.

These are the single source of truth for every enum used across the
broker-agnostic core. Broker-specific status mappers live in each
broker's ``status_mapper.py`` and delegate to :meth:`OrderStatus.normalize`
for canonical values.

**This is a re-export facade**. The actual definitions live in
narrow submodules:

* :mod:`domain.enums` — ``Side``, ``OrderStatus``, ``OrderType``, ``ProductType``, ``Validity``
* :mod:`domain.market_enums` — ``ExchangeSegment``, ``InstrumentType``
* :mod:`domain.capabilities` — ``Capability``, ``ConnectionStatus``
* :mod:`domain.entities.position` — ``PositionState``, ``POSITION_STATE_TRANSITIONS``
* :mod:`domain.entities.order_lifecycle` — ``ORDER_STATUS_TRANSITIONS``

Usage remains unchanged::

    from domain.types import OrderStatus, Side, ExchangeSegment
"""

from __future__ import annotations

from domain.capabilities import Capability, ConnectionStatus
from domain.entities.order_lifecycle import ORDER_STATUS_TRANSITIONS
from domain.entities.position import POSITION_STATE_TRANSITIONS, PositionState
from domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from domain.market_enums import ExchangeSegment, InstrumentType

__all__ = [
    "ORDER_STATUS_TRANSITIONS",
    "POSITION_STATE_TRANSITIONS",
    "Capability",
    "ConnectionStatus",
    "ExchangeSegment",
    "InstrumentType",
    "OrderStatus",
    "OrderType",
    "PositionState",
    "ProductType",
    "Side",
    "Validity",
]

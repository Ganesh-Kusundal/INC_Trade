"""Broker-agnostic core types and interfaces.

This subpackage contains the canonical domain types, abstract interfaces,
and shared utilities used by all broker adapters (Dhan, Upstox, Paper).

Import Direction Rule
---------------------
brokers.common → broker-agnostic core (NEVER imports broker-specific code)
brokers.dhan → Dhan-specific adapter (imports from brokers.common)
brokers.upstox → Upstox-specific adapter (imports from brokers.common)
brokers.paper → Paper/mock trading adapter (imports from brokers.common)
"""

from __future__ import annotations

from brokers.common.factory import BrokerProviderFactory

# Export common interfaces
from brokers.common.gateway import MarketDataGateway

# Export common types
from domain import (
    Balance,
    DepthLevel,
    Holding,
    MarketDepth,
    Order,
    OrderResponse,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Quote,
    Side,
    Trade,
    Validity,
)

# Export field mapping protocol and default implementation
from domain.entities import FieldMapping
from domain.field_mapping import DefaultFieldMapping

# Backward-compatibility alias
OrderSide = Side

__all__ = [
    # Domain types
    "Balance",
    "BrokerProviderFactory",
    "DefaultFieldMapping",
    "DepthLevel",
    # Field mapping
    "FieldMapping",
    "Holding",
    # Abstract interfaces
    "MarketDataGateway",
    "MarketDepth",
    "Order",
    "OrderResponse",
    "OrderSide",  # Backward-compat alias
    "OrderStatus",
    "OrderType",
    "Position",
    "ProductType",
    "Quote",
    "Side",
    "Trade",
    "Validity",
]

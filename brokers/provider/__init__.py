"""Provider abstraction — the single interface for broker IO.

The :class:`Provider` protocol replaces the three-port split
(``MarketDataPort`` + ``TradingPort`` + ``StreamingPort``).
"""

from brokers.provider.composite import CompositeProvider
from brokers.provider.protocol import Provider
from brokers.provider.routing import RoutingStrategy
from brokers.provider.extensions import ExtensionAccess

__all__ = [
    "CompositeProvider",
    "ExtensionAccess",
    "Provider",
    "RoutingStrategy",
]

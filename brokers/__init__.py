"""TradeXV2 Brokers Package — broker-agnostic core.

This package provides the canonical domain types and abstract interfaces
used across all broker adapters. Broker-specific implementations (Dhan,
Upstox, Paper) are in their own subpackages and should be imported directly:

    from brokers.dhan.gateway import BrokerGateway
    from brokers.upstox.gateway import UpstoxGateway
    from brokers.paper import PaperGateway

Import Direction Rule
---------------------
    brokers.common → broker-agnostic core (this package)
    brokers.dhan → Dhan-specific adapter
    brokers.upstox → Upstox-specific adapter
    brokers.paper → Paper/mock trading adapter

Never import broker-specific types from ``brokers`` top-level. This
prevents shotgun surgery when adding new brokers.
"""

# Canonical interfaces (not broker-specific)
from brokers.common.factory import BrokerProviderFactory
from brokers.common.gateway import MarketDataGateway

__all__ = [
    "BrokerProviderFactory",
    # Abstract interfaces
    "MarketDataGateway",
]

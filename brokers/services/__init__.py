"""Domain services — application layer with business logic.

Services depend on ports (abstractions) and provide high-level
functionality to clients. They encapsulate business rules, validation,
and cross-cutting concerns.
"""

from brokers.services.broker_router import BrokerRouter
from brokers.services.capability_discovery import CapabilityDiscovery
from brokers.services.historical_service import HistoricalService
from brokers.services.market_data_service import MarketDataService
from brokers.services.order_service import OrderService
from brokers.services.portfolio_service import PortfolioService
from brokers.services.shadow_broker import ShadowBroker

__all__ = [
    "BrokerRouter",
    "CapabilityDiscovery",
    "HistoricalService",
    "MarketDataService",
    "OrderService",
    "PortfolioService",
    "ShadowBroker",
]

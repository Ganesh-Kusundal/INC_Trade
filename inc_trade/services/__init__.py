"""Domain services — application layer with business logic.

Services depend on ports (abstractions) and provide high-level
functionality to clients. They encapsulate business rules, validation,
and cross-cutting concerns.
"""

from inc_trade.services.broker_router import BrokerRouter
from inc_trade.services.capability_discovery import CapabilityDiscovery
from inc_trade.services.historical_service import HistoricalService
from inc_trade.services.market_data_service import MarketDataService
from inc_trade.services.options_service import OptionsService
from inc_trade.services.order_service import OrderService
from inc_trade.services.order_validator import OrderValidationService
from inc_trade.services.portfolio_service import PortfolioService
from inc_trade.services.shadow_broker import ShadowBroker

__all__ = [
    "BrokerRouter",
    "CapabilityDiscovery",
    "HistoricalService",
    "MarketDataService",
    "OptionsService",
    "OrderService",
    "OrderValidationService",
    "PortfolioService",
    "ShadowBroker",
]

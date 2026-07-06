"""Service factory — domain service creation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

from brokers.adapters.dhan.extensions.forever_orders import DhanForeverOrders
from brokers.adapters.dhan.extensions.margin import DhanMargin
from brokers.adapters.dhan.extensions.super_orders import DhanSuperOrders
from brokers.adapters.dhan.historical import DhanHistorical
from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.adapters.dhan.instruments import DhanInstruments
from brokers.adapters.dhan.market_data import DhanMarketData
from brokers.adapters.dhan.options import DhanOptions
from brokers.adapters.dhan.orders import DhanOrders
from brokers.adapters.dhan.portfolio import DhanPortfolio

if TYPE_CHECKING:
    from brokers.ports.event_publisher import EventPublisherPort
    from brokers.ports.risk_manager import RiskManagerPort


class ServiceComponents(NamedTuple):
    """Domain service components."""

    resolver: DhanInstrumentResolver
    orders: DhanOrders
    market_data: DhanMarketData
    portfolio: DhanPortfolio
    instruments: DhanInstruments
    historical: DhanHistorical
    options: DhanOptions
    margin: DhanMargin
    forever_orders: DhanForeverOrders
    super_orders: DhanSuperOrders


def create_services(
    http_client: Any,
    event_bus: EventPublisherPort | None = None,
    risk_manager: RiskManagerPort | None = None,
) -> ServiceComponents:
    """Create all domain services.

    Args:
        http_client: HTTP client for API calls.
        event_bus: Optional event publisher.
        risk_manager: Optional risk manager.

    Returns:
        ServiceComponents namedtuple with all domain services.
    """
    resolver = DhanInstrumentResolver()
    orders = DhanOrders(
        http_client,
        resolver,
        event_bus=event_bus,
        risk_manager=risk_manager,
    )
    market_data = DhanMarketData(http_client, resolver)
    portfolio = DhanPortfolio(http_client)
    instruments = DhanInstruments(resolver)
    historical = DhanHistorical(http_client, resolver)
    options = DhanOptions(http_client, instruments)

    # Extensions
    margin = DhanMargin(http_client, resolver)
    forever_orders = DhanForeverOrders(http_client, resolver)
    super_orders = DhanSuperOrders(http_client, resolver)

    return ServiceComponents(
        resolver=resolver,
        orders=orders,
        market_data=market_data,
        portfolio=portfolio,
        instruments=instruments,
        historical=historical,
        options=options,
        margin=margin,
        forever_orders=forever_orders,
        super_orders=super_orders,
    )

"""Native CommonBrokerGateway exposure for legacy sync gateways."""

from __future__ import annotations

from brokers.common.adapters.market_data_gateway_adapter import (
    MarketDataGatewayAdapter,
    wrap_market_gateway,
)
from brokers.common.broker_port import CommonBrokerGateway
from brokers.common.gateway import MarketDataGateway


def to_common_broker_gateway(
    gateway: MarketDataGateway,
    broker_id: str,
    *,
    extensions: frozenset[str] | None = None,
) -> CommonBrokerGateway:
    """Return a CommonBrokerGateway port for a sync MarketDataGateway."""
    if isinstance(gateway, CommonBrokerGateway):
        return gateway
    existing = getattr(gateway, "_common_broker_gateway", None)
    if isinstance(existing, MarketDataGatewayAdapter):
        return existing
    adapter = wrap_market_gateway(gateway, broker_id, extensions=extensions)
    setattr(gateway, "_common_broker_gateway", adapter)
    return adapter


def resolve_common_gateways(
    gateways: list[tuple[str, MarketDataGateway]],
) -> list[tuple[str, CommonBrokerGateway]]:
    """Convert legacy gateway tuples to CommonBrokerGateway ports."""
    resolved: list[tuple[str, CommonBrokerGateway]] = []
    for broker_id, gateway in gateways:
        resolved.append((broker_id, to_common_broker_gateway(gateway, broker_id)))
    return resolved

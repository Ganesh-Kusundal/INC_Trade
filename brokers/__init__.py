"""Brokers module — Clean Architecture broker integration framework.

Usage::

    from brokers import create_broker

    gw = create_broker("dhan", access_token="...", client_id="...")
    gw = create_broker("upstox", access_token="...")
    gw = create_broker("paper")
"""

from __future__ import annotations

from typing import Any

from brokers.domain import (
    Balance as Balance,
    DepthLevel as DepthLevel,
    Holding as Holding,
    MarketDepth as MarketDepth,
    Order as Order,
    OrderResponse as OrderResponse,
    Position as Position,
    Quote as Quote,
    Trade as Trade,
)
from brokers.domain.enums import (
    OrderStatus as OrderStatus,
    OrderType as OrderType,
    ProductType as ProductType,
    Side as Side,
    Validity as Validity,
)
from brokers.domain.exceptions import (
    AuthenticationError as AuthenticationError,
    BrokerError as BrokerError,
    CircuitOpenError as CircuitOpenError,
    InstrumentNotFoundError as InstrumentNotFoundError,
    OrderRejectedError as OrderRejectedError,
    RateLimitError as RateLimitError,
)
from brokers.ports import (
    AuthPort as AuthPort,
    BrokerGateway as BrokerGateway,
    InstrumentInfo as InstrumentInfo,
    InstrumentPort as InstrumentPort,
    MarketDataPort as MarketDataPort,
    OrderExecutionPort as OrderExecutionPort,
    PortfolioPort as PortfolioPort,
)


def create_broker(name: str, **credentials: Any) -> BrokerGateway:
    """Factory — create a broker gateway by name.

    Args:
        name: Broker name — "dhan", "upstox", or "paper".
        **credentials: Broker-specific credentials.
            - dhan: access_token, client_id
            - upstox: access_token
            - paper: initial_cash (optional)

    Returns:
        A BrokerGateway instance.

    Raises:
        ValueError: If broker name is unknown.
    """
    name = name.lower().strip()
    if name == "dhan":
        from brokers.adapters.dhan.gateway import DhanGateway

        return DhanGateway(
            access_token=credentials["access_token"],
            client_id=credentials["client_id"],
        )
    if name == "upstox":
        from brokers.adapters.upstox.gateway import UpstoxGateway

        return UpstoxGateway(access_token=credentials["access_token"])
    if name == "paper":
        from decimal import Decimal
        from brokers.adapters.paper.gateway import PaperGateway

        initial_cash = credentials.get("initial_cash")
        if initial_cash is not None:
            return PaperGateway(initial_cash=Decimal(str(initial_cash)))
        return PaperGateway()
    raise ValueError(f"Unknown broker: {name!r}. Choose from: dhan, upstox, paper")

"""Brokers module — Clean Architecture broker integration framework.

Usage::

    from brokers import create_broker

    gw = create_broker("dhan", access_token="...", client_id="...")
    gw = create_broker("upstox", access_token="...")
    gw = create_broker("paper")
"""

from __future__ import annotations

import warnings
from typing import Any, cast

from inc_trade.domain import (
    Balance as Balance,
)
from inc_trade.domain import (
    DepthLevel as DepthLevel,
)
from inc_trade.domain import (
    Holding as Holding,
)
from inc_trade.domain import (
    MarketDepth as MarketDepth,
)
from inc_trade.domain import (
    Order as Order,
)
from inc_trade.domain import (
    OrderResponse as OrderResponse,
)
from inc_trade.domain import (
    Position as Position,
)
from inc_trade.domain import (
    Quote as Quote,
)
from inc_trade.domain import (
    Trade as Trade,
)
from inc_trade.domain.enums import (
    BrokerID as BrokerID,
)
from inc_trade.domain.enums import (
    OrderStatus as OrderStatus,
)
from inc_trade.domain.enums import (
    OrderType as OrderType,
)
from inc_trade.domain.enums import (
    ProductType as ProductType,
)
from inc_trade.domain.enums import (
    Side as Side,
)
from inc_trade.domain.enums import (
    Validity as Validity,
)
from inc_trade.domain.exceptions import (
    AuthenticationError as AuthenticationError,
)
from inc_trade.domain.exceptions import (
    BrokerDegradedError as BrokerDegradedError,
)
from inc_trade.domain.exceptions import (
    BrokerError as BrokerError,
)
from inc_trade.domain.exceptions import (
    BrokerServerError as BrokerServerError,
)
from inc_trade.domain.exceptions import (
    CircuitOpenError as CircuitOpenError,
)
from inc_trade.domain.exceptions import (
    ConfigError as ConfigError,
)
from inc_trade.domain.exceptions import (
    DataError as DataError,
)
from inc_trade.domain.exceptions import (
    InstrumentNotFoundError as InstrumentNotFoundError,
)
from inc_trade.domain.exceptions import (
    NetworkError as NetworkError,
)
from inc_trade.domain.exceptions import (
    NonRetryableError as NonRetryableError,
)
from inc_trade.domain.exceptions import (
    NotSupportedError as NotSupportedError,
)
from inc_trade.domain.exceptions import (
    OrderRejectedError as OrderRejectedError,
)
from inc_trade.domain.exceptions import (
    RateLimitError as RateLimitError,
)
from inc_trade.domain.exceptions import (
    RetryableError as RetryableError,
)
from inc_trade.domain.exceptions import (
    TokenRateLimitError as TokenRateLimitError,
)
from inc_trade.domain.exceptions import (
    TradeXV2Error as TradeXV2Error,
)
from inc_trade.domain.exceptions import (
    ValidationError as ValidationError,
)
from inc_trade.ports import (
    AuthPort as AuthPort,
)
from inc_trade.ports import (
    BrokerGateway as BrokerGateway,
)
from inc_trade.ports import (
    ClockPort as ClockPort,
)
from inc_trade.ports import (
    HistoricalPort as HistoricalPort,
)
from inc_trade.ports import (
    InstrumentInfo as InstrumentInfo,
)
from inc_trade.ports import (
    InstrumentPort as InstrumentPort,
)
from inc_trade.ports import (
    MarketDataPort as MarketDataPort,
)
from inc_trade.ports import (
    OrderExecutionPort as OrderExecutionPort,
)
from inc_trade.ports import (
    PortfolioPort as PortfolioPort,
)
from inc_trade.ports import (
    StreamingPort as StreamingPort,
)
from inc_trade.services.broker_facade import (
    BrokerFacade as BrokerFacade,
)
from inc_trade.services.broker_session import BrokerSession as BrokerSession


def create_broker(
    name: str | BrokerID,
    allow_live_orders: bool = False,
    env_path: str | None = None,
    token_state_dir: str | None = None,
    auto_refresh: bool = True,
    lifecycle: Any | None = None,
    **credentials: Any,
) -> "BrokerFacade":
    """Factory — create a broker facade by name.

    .. deprecated::
        Use :func:`brokers.connect()` instead.

    Returns a BrokerFacade that enforces service layer usage.

    Args:
        name: Broker name — "dhan", "upstox", or "paper" (str or BrokerID).
        allow_live_orders: Enable live order placement (kill switch). Defaults to False for safety.
        env_path: Path to .env file for token persistence (Dhan only).
        token_state_dir: Directory for JSON token state persistence (Dhan only).
        auto_refresh: Enable background token refresh scheduler (Dhan only).
        lifecycle: Optional lifecycle manager to register scheduler with (Dhan only).
        **credentials: Broker-specific credentials.
            - dhan: access_token, client_id, pin, totp_secret
            - upstox: access_token
            - paper: initial_cash (optional)

    Returns:
        A BrokerFacade instance wrapping the underlying gateway.

    Raises:
        ValueError: If broker name is unknown.
    """
    warnings.warn(
        "create_broker() is deprecated, use brokers.connect() instead",
        DeprecationWarning,
        stacklevel=2,
    )
    from pathlib import Path

    from inc_trade.services.broker_facade import BrokerFacade

    # Normalize BrokerID enum to string
    if isinstance(name, BrokerID):
        name = name.value
    name = name.lower().strip()
    if name == "dhan":
        from brokers.adapters.dhan.gateway import DhanGateway

        dhan_gw = DhanGateway(
            access_token=credentials.get("access_token"),
            client_id=credentials.get("client_id"),
            pin=credentials.get("pin"),
            totp_secret=credentials.get("totp_secret"),
            allow_live_orders=allow_live_orders,
            env_path=Path(env_path) if env_path else None,
            token_state_dir=Path(token_state_dir) if token_state_dir else None,
            auto_refresh=auto_refresh,
            lifecycle=lifecycle,
        )
        from inc_trade.ports.capabilities import (
            ForeverOrderProvider,
            KillSwitchProvider,
            MarginProvider,
            SliceOrderProvider,
            SuperOrderProvider,
        )
        from inc_trade.ports.extension_registry import DictExtensionRegistry

        registry = DictExtensionRegistry()
        registry.register("dhan", cast(type, KillSwitchProvider), dhan_gw.orders)
        registry.register("dhan", cast(type, SliceOrderProvider), dhan_gw.orders)
        registry.register("dhan", MarginProvider, dhan_gw.margin)
        registry.register("dhan", ForeverOrderProvider, dhan_gw.forever_orders)
        registry.register("dhan", SuperOrderProvider, dhan_gw.super_orders)

        return BrokerFacade(
            cast(BrokerGateway, dhan_gw),
            allow_live_orders=allow_live_orders,
            extension_registry=registry,
        )
    if name == "upstox":
        from brokers.adapters.upstox.gateway import UpstoxGateway

        upstox_gw = UpstoxGateway(
            access_token=credentials["access_token"],
            allow_live_orders=allow_live_orders,
        )
        from inc_trade.ports.capabilities import GTTProvider, NewsProvider
        from inc_trade.ports.extension_registry import DictExtensionRegistry

        registry = DictExtensionRegistry()
        registry.register("upstox", cast(type, NewsProvider), upstox_gw.news)
        registry.register("upstox", cast(type, GTTProvider), upstox_gw.gtt)
        return BrokerFacade(
            cast(BrokerGateway, upstox_gw),
            allow_live_orders=allow_live_orders,
            extension_registry=registry,
        )
    if name == "paper":
        from decimal import Decimal

        from brokers.adapters.paper.gateway import PaperGateway

        initial_cash = credentials.get("initial_cash")
        if initial_cash is not None:
            paper_gw = PaperGateway(initial_cash=Decimal(str(initial_cash)))
        else:
            paper_gw = PaperGateway()
        from inc_trade.ports.extension_registry import DictExtensionRegistry

        registry = DictExtensionRegistry()
        return BrokerFacade(
            cast(BrokerGateway, paper_gw),
            allow_live_orders=allow_live_orders,
            extension_registry=registry,
        )
    raise ValueError(f"Unknown broker: {name!r}. Choose from: dhan, upstox, paper")


def connect(
    name: str | BrokerID,
    allow_live_orders: bool = False,
    env_path: str | None = None,
    token_state_dir: str | None = None,
    auto_refresh: bool = True,
    lifecycle: Any | None = None,
    **credentials: Any,
) -> BrokerSession:
    """Create a BrokerSession — the recommended public API.

    Wraps create_broker() and returns a typed BrokerSession composition root
    with named port properties (orders, market, streaming, auth, portfolio, historical).

    Example::

        broker = brokers.connect("paper")
        broker.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)

        broker = brokers.connect("dhan", access_token="...", client_id="...")
        broker.streaming.subscribe("NSE:RELIANCE", on_tick)
        broker.close()
    """
    from inc_trade.services.audit_facade import AuditFacade
    from inc_trade.trading.order_repository import OrderRepository

    facade = create_broker(
        name,
        allow_live_orders=allow_live_orders,
        env_path=env_path,
        token_state_dir=token_state_dir,
        auto_refresh=auto_refresh,
        lifecycle=lifecycle,
        **credentials,
    )
    broker_id_str = name.value if isinstance(name, BrokerID) else str(name)
    return BrokerSession(
        broker_id=broker_id_str,
        facade=facade,
        audit=AuditFacade(OrderRepository()),
    )

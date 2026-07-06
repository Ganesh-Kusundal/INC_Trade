"""Brokers module — Clean Architecture broker integration framework.

Usage::

    from brokers import connect

    broker = connect("dhan", access_token="...", client_id="...")
    broker = connect("upstox", access_token="...")
    broker = connect("paper")
"""

from __future__ import annotations

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


def _build_facade(
    name: str | BrokerID,
    allow_live_orders: bool = False,
    env_path: str | None = None,
    token_state_dir: str | None = None,
    auto_refresh: bool = True,
    lifecycle: Any | None = None,
    **credentials: Any,
) -> BrokerFacade:
    """Build a BrokerFacade for the given broker name."""
    from pathlib import Path

    from inc_trade.services.broker_facade import BrokerFacade

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
        registry.register("dhan", cast("type", KillSwitchProvider), dhan_gw.orders)
        registry.register("dhan", cast("type", SliceOrderProvider), dhan_gw.orders)
        registry.register("dhan", MarginProvider, dhan_gw.margin)
        registry.register("dhan", ForeverOrderProvider, dhan_gw.forever_orders)
        registry.register("dhan", SuperOrderProvider, dhan_gw.super_orders)

        return BrokerFacade(
            dhan_gw,
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
        registry.register("upstox", cast("type", NewsProvider), upstox_gw.news)
        registry.register("upstox", cast("type", GTTProvider), upstox_gw.gtt)
        return BrokerFacade(
            upstox_gw,
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
            paper_gw,
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
    """Create a BrokerSession — the primary public API.

    Returns a typed BrokerSession composition root with named port
    properties (orders, market, streaming, auth, portfolio, historical).

    Example::

        broker = brokers.connect("paper")
        broker.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)

        broker = brokers.connect("dhan", access_token="...", client_id="...")
        broker.streaming.subscribe("NSE:RELIANCE", on_tick)
        broker.close()
    """
    from inc_trade.services.audit_facade import AuditFacade
    from inc_trade.trading.order_repository import OrderRepository

    facade = _build_facade(
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

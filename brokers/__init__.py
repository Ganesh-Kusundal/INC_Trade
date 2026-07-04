"""Brokers module — Clean Architecture broker integration framework.

Usage::

    from brokers import create_broker

    gw = create_broker("dhan", access_token="...", client_id="...")
    gw = create_broker("upstox", access_token="...")
    gw = create_broker("paper")
"""

from __future__ import annotations

from typing import Any, cast

from brokers.domain import (
    Balance as Balance,
)
from brokers.domain import (
    DepthLevel as DepthLevel,
)
from brokers.domain import (
    Holding as Holding,
)
from brokers.domain import (
    MarketDepth as MarketDepth,
)
from brokers.domain import (
    Order as Order,
)
from brokers.domain import (
    OrderResponse as OrderResponse,
)
from brokers.domain import (
    Position as Position,
)
from brokers.domain import (
    Quote as Quote,
)
from brokers.domain import (
    Trade as Trade,
)
from brokers.domain.enums import (
    BrokerID as BrokerID,
)
from brokers.domain.enums import (
    OrderStatus as OrderStatus,
)
from brokers.domain.enums import (
    OrderType as OrderType,
)
from brokers.domain.enums import (
    ProductType as ProductType,
)
from brokers.domain.enums import (
    Side as Side,
)
from brokers.domain.enums import (
    Validity as Validity,
)
from brokers.domain.exceptions import (
    AuthenticationError as AuthenticationError,
)
from brokers.domain.exceptions import (
    BrokerDegradedError as BrokerDegradedError,
)
from brokers.domain.exceptions import (
    BrokerError as BrokerError,
)
from brokers.domain.exceptions import (
    BrokerServerError as BrokerServerError,
)
from brokers.domain.exceptions import (
    CircuitOpenError as CircuitOpenError,
)
from brokers.domain.exceptions import (
    ConfigError as ConfigError,
)
from brokers.domain.exceptions import (
    DataError as DataError,
)
from brokers.domain.exceptions import (
    InstrumentNotFoundError as InstrumentNotFoundError,
)
from brokers.domain.exceptions import (
    NetworkError as NetworkError,
)
from brokers.domain.exceptions import (
    NonRetryableError as NonRetryableError,
)
from brokers.domain.exceptions import (
    NotSupportedError as NotSupportedError,
)
from brokers.domain.exceptions import (
    OrderRejectedError as OrderRejectedError,
)
from brokers.domain.exceptions import (
    RateLimitError as RateLimitError,
)
from brokers.domain.exceptions import (
    RetryableError as RetryableError,
)
from brokers.domain.exceptions import (
    TokenRateLimitError as TokenRateLimitError,
)
from brokers.domain.exceptions import (
    TradeXV2Error as TradeXV2Error,
)
from brokers.domain.exceptions import (
    ValidationError as ValidationError,
)
from brokers.ports import (
    AuthPort as AuthPort,
)
from brokers.ports import (
    BrokerGateway as BrokerGateway,
)
from brokers.ports import (
    ClockPort as ClockPort,
)
from brokers.ports import (
    HistoricalPort as HistoricalPort,
)
from brokers.ports import (
    InstrumentInfo as InstrumentInfo,
)
from brokers.ports import (
    InstrumentPort as InstrumentPort,
)
from brokers.ports import (
    MarketDataPort as MarketDataPort,
)
from brokers.ports import (
    OrderExecutionPort as OrderExecutionPort,
)
from brokers.ports import (
    PortfolioPort as PortfolioPort,
)
from brokers.ports import (
    StreamingPort as StreamingPort,
)
from brokers.services.broker_facade import (
    BrokerFacade as BrokerFacade,
)
from brokers.services.broker_session import BrokerSession as BrokerSession


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
    from pathlib import Path

    from brokers.services.broker_facade import BrokerFacade

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
        from brokers.ports.extension_registry import DictExtensionRegistry
        from brokers.ports.capabilities import (
            KillSwitchProvider,
            SliceOrderProvider,
            MarginProvider,
            ForeverOrderProvider,
            SuperOrderProvider,
        )

        registry = DictExtensionRegistry()
        registry.register("dhan", cast(type, KillSwitchProvider), dhan_gw.orders)
        registry.register("dhan", cast(type, SliceOrderProvider), dhan_gw.orders)
        registry.register("dhan", MarginProvider, dhan_gw.margin)
        registry.register("dhan", ForeverOrderProvider, dhan_gw.forever_orders)
        registry.register("dhan", SuperOrderProvider, dhan_gw.super_orders)

        return BrokerFacade(cast(BrokerGateway, dhan_gw), allow_live_orders=allow_live_orders, extension_registry=registry)
    if name == "upstox":
        from brokers.adapters.upstox.gateway import UpstoxGateway

        upstox_gw = UpstoxGateway(
            access_token=credentials["access_token"],
            allow_live_orders=allow_live_orders,
        )
        from brokers.ports.extension_registry import DictExtensionRegistry
        from brokers.ports.capabilities import NewsProvider, GTTProvider
        registry = DictExtensionRegistry()
        registry.register("upstox", cast(type, NewsProvider), upstox_gw.news)
        registry.register("upstox", cast(type, GTTProvider), upstox_gw.gtt)
        return BrokerFacade(cast(BrokerGateway, upstox_gw), allow_live_orders=allow_live_orders, extension_registry=registry)
    if name == "paper":
        from decimal import Decimal

        from brokers.adapters.paper.gateway import PaperGateway

        initial_cash = credentials.get("initial_cash")
        if initial_cash is not None:
            paper_gw = PaperGateway(initial_cash=Decimal(str(initial_cash)))
        else:
            paper_gw = PaperGateway()
        from brokers.ports.extension_registry import DictExtensionRegistry
        registry = DictExtensionRegistry()
        return BrokerFacade(cast(BrokerGateway, paper_gw), allow_live_orders=allow_live_orders, extension_registry=registry)
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
    )


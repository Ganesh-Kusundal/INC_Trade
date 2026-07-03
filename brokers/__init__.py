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
    BrokerDegradedError as BrokerDegradedError,
    BrokerError as BrokerError,
    BrokerServerError as BrokerServerError,
    CircuitOpenError as CircuitOpenError,
    ConfigError as ConfigError,
    DataError as DataError,
    InstrumentNotFoundError as InstrumentNotFoundError,
    NetworkError as NetworkError,
    NonRetryableError as NonRetryableError,
    NotSupportedError as NotSupportedError,
    OrderRejectedError as OrderRejectedError,
    RateLimitError as RateLimitError,
    RetryableError as RetryableError,
    TokenRateLimitError as TokenRateLimitError,
    TradeXV2Error as TradeXV2Error,
    ValidationError as ValidationError,
)
from brokers.ports import (
    AuthPort as AuthPort,
    BrokerGateway as BrokerGateway,
    ClockPort as ClockPort,
    HistoricalPort as HistoricalPort,
    InstrumentInfo as InstrumentInfo,
    InstrumentPort as InstrumentPort,
    MarketDataPort as MarketDataPort,
    OrderExecutionPort as OrderExecutionPort,
    PortfolioPort as PortfolioPort,
    StreamingPort as StreamingPort,
)


def create_broker(
    name: str,
    allow_live_orders: bool = False,
    env_path: str | None = None,
    token_state_dir: str | None = None,
    auto_refresh: bool = True,
    lifecycle: Any | None = None,
    **credentials: Any,
) -> BrokerGateway:
    """Factory — create a broker gateway by name.

    Args:
        name: Broker name — "dhan", "upstox", or "paper".
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
        A BrokerGateway instance.

    Raises:
        ValueError: If broker name is unknown.
    """
    from pathlib import Path

    name = name.lower().strip()
    if name == "dhan":
        from brokers.adapters.dhan.gateway import DhanGateway

        return DhanGateway(
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
    if name == "upstox":
        from brokers.adapters.upstox.gateway import UpstoxGateway

        return UpstoxGateway(
            access_token=credentials["access_token"],
            allow_live_orders=allow_live_orders,
        )
    if name == "paper":
        from decimal import Decimal
        from brokers.adapters.paper.gateway import PaperGateway

        initial_cash = credentials.get("initial_cash")
        if initial_cash is not None:
            return PaperGateway(initial_cash=Decimal(str(initial_cash)))
        return PaperGateway()
    raise ValueError(f"Unknown broker: {name!r}. Choose from: dhan, upstox, paper")

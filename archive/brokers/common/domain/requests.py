"""Canonical request/input shapes for broker operations.

These dataclasses represent the *input* side of broker operations —
order placement, modification, preview, and historical data queries.
They are distinct from the *output* models in ``models.py``.

Transport-only fields (``exchange_segment``, ``is_amo``, ``algo_name``,
``market_protection``, ``transport_only``) have been moved to
:class:`brokers.common.dtos.BrokerOrderPayload`, which extends
``OrderRequest`` with broker-transport metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from domain.types import (
    OrderType,
    ProductType,
    Side,
    Validity,
)


@dataclass(slots=True, frozen=True)
class OrderRequest:
    """Input model for placing an order — domain fields only.

    Immutable by design. Broker-transport fields (exchange_segment, is_amo, etc.)
    have been moved to :class:`brokers.common.dtos.BrokerOrderPayload`.
    Domain-level consumers (``OrderManager``, ``RiskManager``,
    ``OrderRepository``) should accept ``OrderRequest``; broker adapters that
    need transport metadata should accept ``BrokerOrderPayload``.
    """

    security_id: str = ""
    symbol: str = ""
    exchange: str = "NSE"
    transaction_type: Side = Side.BUY
    quantity: int = 0
    price: Decimal = Decimal("0")
    trigger_price: Decimal | None = None
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    correlation_id: str | None = None
    tag: str | None = None
    slice: bool = False


@dataclass(slots=True, frozen=True)
class ModifyOrderRequest:
    """Input model for modifying an existing order."""

    order_id: str
    quantity: int | None = None
    price: Decimal | None = None
    trigger_price: Decimal | None = None
    order_type: OrderType | None = None
    validity: Validity | None = None
    product_type: ProductType | None = None


@dataclass(slots=True, frozen=True)
class SliceOrderRequest:
    """Request for splitting a large order into child orders."""

    symbol: str = ""
    exchange: str = "NSE"
    side: Side = Side.BUY
    quantity: int = 0
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY


@dataclass(slots=True, frozen=True)
class OrderPreview:
    """Outcome of pre-flight order validation."""

    valid: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notional: Decimal | None = None
    margin_required: Decimal | None = None


@dataclass(slots=True, frozen=True)
class HistoricalCandle:
    """A single OHLCV candle returned by the historical-data endpoint."""

    timestamp: datetime | None = None
    symbol: str = ""
    exchange: str = "NSE"
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    open_interest: int = 0
    timeframe: str = "1D"

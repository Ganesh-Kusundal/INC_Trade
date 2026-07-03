"""Domain models for unified order requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from brokers.domain.enums import OrderType, ProductType, Side, Validity


@dataclass(frozen=True, kw_only=True)
class OrderRequest:
    """Base class for all order requests."""
    
    symbol: str
    exchange: str
    side: Side
    quantity: int
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    correlation_id: str = ""
    order_type: OrderType = field(init=False)


@dataclass(frozen=True, kw_only=True)
class MarketOrder(OrderRequest):
    """A request to buy or sell at the current market price."""
    
    order_type: OrderType = field(default=OrderType.MARKET, init=False)


@dataclass(frozen=True, kw_only=True)
class LimitOrder(OrderRequest):
    """A request to buy or sell at a specific price or better."""
    
    price: Decimal
    order_type: OrderType = field(default=OrderType.LIMIT, init=False)


@dataclass(frozen=True, kw_only=True)
class StopMarketOrder(OrderRequest):
    """A request to buy or sell at the market price once a trigger price is reached."""
    
    trigger_price: Decimal
    order_type: OrderType = field(default=OrderType.STOP_LOSS_MARKET, init=False)


@dataclass(frozen=True, kw_only=True)
class StopLimitOrder(OrderRequest):
    """A request to buy or sell at a specific price once a trigger price is reached."""
    
    price: Decimal
    trigger_price: Decimal
    order_type: OrderType = field(default=OrderType.STOP_LOSS, init=False)

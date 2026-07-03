"""Upstox DTO → domain entity mapper.

Converts raw Upstox API responses into frozen domain value objects.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, cast

from brokers.domain import (
    Balance,
    DepthLevel,
    Holding,
    MarketDepth,
    Order,
    OrderResponse,
    Position,
    Quote,
    Trade,
)
from brokers.domain.enums import (
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from brokers.adapters.upstox.config import (
    ORDER_TYPE_MAP_REVERSE as _ORDER_TYPE_MAP,
    PRODUCT_MAP_REVERSE as _PRODUCT_MAP,
    SIDE_MAP_REVERSE as _SIDE_MAP,
    STATUS_MAP as _STATUS_MAP,
    VALIDITY_MAP_REVERSE as _VALIDITY_MAP,
)
from brokers.utils.price import to_decimal


def unwrap_data(response: dict[str, Any], default: Any = None) -> Any:
    """Extract the 'data' field from an Upstox API response.

    Upstox wraps all responses in {"data": ...}. This helper
    unwraps that envelope, returning `default` if missing.
    """
    if default is None:
        default = []
    if isinstance(response, dict):
        return response.get("data", default)
    return default


def map_order(data: dict[str, Any]) -> Order:
    status_raw = str(data.get("status", "")).upper()
    return Order(
        order_id=str(data.get("order_id", "")),
        symbol=data.get("trading_symbol", data.get("symbol", "")),
        exchange=data.get("exchange", ""),
        side=cast(Side, _SIDE_MAP.get(str(data.get("transaction_type", "BUY")).upper(), Side.BUY)),
        quantity=int(data.get("quantity", 0)),
        filled_quantity=int(data.get("filled_quantity", 0)),
        price=to_decimal(data.get("price")),
        trigger_price=to_decimal(data.get("trigger_price")),
        order_type=cast(OrderType, _ORDER_TYPE_MAP.get(
            str(data.get("order_type", "MARKET")).upper(), OrderType.MARKET
        )),
        product_type=cast(ProductType, _PRODUCT_MAP.get(
            str(data.get("product", "I")).upper(), ProductType.INTRADAY
        )),
        validity=cast(Validity, _VALIDITY_MAP.get(
            str(data.get("validity", "DAY")).upper(), Validity.DAY
        )),
        status=cast(OrderStatus, _STATUS_MAP.get(status_raw, OrderStatus.OPEN)),
        message=data.get("status_message", ""),
    )


def map_order_response(data: dict[str, Any]) -> OrderResponse:
    if isinstance(data, dict) and "data" in data:
        inner = data["data"]
        if isinstance(inner, dict):
            order_id = str(inner.get("order_id", ""))
        else:
            order_id = str(data.get("order_id", ""))
    elif isinstance(data, dict):
        order_id = str(data.get("order_id", ""))
    else:
        return OrderResponse.fail("Order failed: unexpected response")

    errors = data.get("errors")
    if errors and isinstance(errors, list):
        first = errors[0] if errors else {}
        msg = (
            first.get("message", "Order rejected")
            if isinstance(first, dict)
            else str(first)
        )
        return OrderResponse.fail(message=msg)

    if not order_id:
        return OrderResponse.fail("Order failed: no order_id in response")

    return OrderResponse(
        order_id=order_id,
        success=True,
        status=OrderStatus.OPEN,
        message=str(data.get("data", "")),
    )


def map_quote(symbol: str, data: dict[str, Any]) -> Quote:
    ohlc = data.get("ohlc", {})
    return Quote(
        symbol=symbol,
        ltp=to_decimal(data.get("last_price", 0)),
        open=to_decimal(ohlc.get("open", 0)),
        high=to_decimal(ohlc.get("high", 0)),
        low=to_decimal(ohlc.get("low", 0)),
        close=to_decimal(ohlc.get("close", 0)),
        volume=int(data.get("volume", 0)),
    )


def map_depth(symbol: str, data: dict[str, Any]) -> MarketDepth:
    depth = data.get("depth", {})
    bid_list = depth.get("buy", []) if isinstance(depth, dict) else []
    ask_list = depth.get("sell", []) if isinstance(depth, dict) else []

    bids = [
        DepthLevel(
            price=to_decimal(level.get("price", 0)),
            quantity=int(level.get("quantity", 0)),
            orders=int(level.get("orders", 0)),
        )
        for level in bid_list
        if isinstance(level, dict)
    ]
    asks = [
        DepthLevel(
            price=to_decimal(level.get("price", 0)),
            quantity=int(level.get("quantity", 0)),
            orders=int(level.get("orders", 0)),
        )
        for level in ask_list
        if isinstance(level, dict)
    ]
    return MarketDepth(symbol=symbol, bids=bids, asks=asks)


def map_position(data: dict[str, Any]) -> Position:
    return Position(
        symbol=data.get("trading_symbol", data.get("symbol", "")),
        exchange=data.get("exchange", ""),
        quantity=int(data.get("net_quantity", data.get("quantity", 0))),
        product_type=cast(ProductType, _PRODUCT_MAP.get(
            str(data.get("product", "I")).upper(), ProductType.INTRADAY
        )),
        average_price=to_decimal(
            data.get("buy_average_price", data.get("average_price", 0))
        ),
        realized_pnl=to_decimal(data.get("realised", 0)),
        unrealized_pnl=to_decimal(data.get("unrealised", 0)),
    )


def map_holding(data: dict[str, Any]) -> Holding:
    return Holding(
        symbol=data.get("trading_symbol", data.get("symbol", "")),
        exchange=data.get("exchange", ""),
        quantity=int(data.get("quantity", 0)),
        average_price=to_decimal(data.get("average_price", 0)),
        isin=data.get("isin", ""),
        t1_quantity=int(data.get("t1_quantity", 0)),
    )


def map_balance(data: dict[str, Any]) -> Balance:
    if "data" in data:
        inner = data["data"]
        if isinstance(inner, dict):
            equity = inner.get("equity", inner)
        else:
            equity = {}
    else:
        equity = data.get("equity", data)

    if not isinstance(equity, dict):
        return Balance(available_cash=Decimal("0"))

    return Balance(
        available_cash=to_decimal(
            equity.get("available_margin", equity.get("available_cash", 0))
        ),
        utilized_margin=to_decimal(equity.get("used_margin", 0)),
        total_margin=to_decimal(equity.get("net_margin", equity.get("net", 0))),
    )


def map_trade(data: dict[str, Any]) -> Trade:
    return Trade(
        trade_id=str(data.get("trade_id", "")),
        order_id=str(data.get("order_id", "")),
        symbol=data.get("trading_symbol", data.get("symbol", "")),
        exchange=data.get("exchange", ""),
        side=cast(Side, _SIDE_MAP.get(str(data.get("transaction_type", "BUY")).upper(), Side.BUY)),
        quantity=int(data.get("quantity", data.get("traded_quantity", 0))),
        price=to_decimal(data.get("average_price", data.get("price", 0))),
    )

"""Dhan DTO → domain entity mapper.

Converts raw Dhan API responses into frozen domain value objects.
"""

from __future__ import annotations

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
from brokers.utils.price import to_decimal

from brokers.adapters.dhan.config import SEGMENT_TO_EXCHANGE

_STATUS_MAP = {
    "PENDING": OrderStatus.PENDING,
    "OPEN": OrderStatus.OPEN,
    "PARTIAL": OrderStatus.PARTIALLY_FILLED,
    "FILLED": OrderStatus.FILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "CANCEL": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
    "INVALID": OrderStatus.REJECTED,
}

_ORDER_TYPE_MAP = {
    1: OrderType.MARKET,
    2: OrderType.LIMIT,
    3: OrderType.STOP_LOSS,
    4: OrderType.STOP_LOSS_MARKET,
}

_SIDE_MAP = {1: Side.BUY, 2: Side.SELL}

_PRODUCT_MAP = {
    "INTRADAY": ProductType.INTRADAY,
    "MARGIN": ProductType.DELIVERY,
    "CNC": ProductType.DELIVERY,
}


def map_order(data: dict) -> Order:
    status_raw = data.get("orderStatus", "PENDING").upper()
    return Order(
        order_id=str(data.get("orderId", "")),
        symbol=data.get("tradingSymbol", ""),
        exchange=_normalize_exchange(data.get("exchangeSegment", "")),
        side=_SIDE_MAP.get(data.get("transactionType", 1), Side.BUY),
        quantity=int(data.get("quantity", 0)),
        filled_quantity=int(data.get("filledQty", 0)),
        price=to_decimal(data.get("price")),
        trigger_price=to_decimal(data.get("triggerPrice")),
        order_type=_ORDER_TYPE_MAP.get(data.get("orderType", 1), OrderType.MARKET),
        product_type=_PRODUCT_MAP.get(
            data.get("productType", "INTRADAY"), ProductType.INTRADAY
        ),
        validity=Validity.DAY,
        status=_STATUS_MAP.get(status_raw, OrderStatus.PENDING),
        message=data.get("rejectReason", ""),
    )


def map_order_response(data: dict) -> OrderResponse:
    order_id = str(data.get("orderId", ""))
    status = data.get("orderStatus", "")
    if status.upper() in ("REJECTED", "INVALID"):
        return OrderResponse.fail(
            message=data.get("rejectReason", "Order rejected"),
            error_code=str(data.get("errorCode", "")),
        )
    return OrderResponse(
        order_id=order_id,
        success=bool(order_id),
        status=_STATUS_MAP.get(status.upper(), OrderStatus.PENDING),
        message=data.get("rejectReason", ""),
    )


def map_quote(symbol: str, data: dict) -> Quote:
    last = data.get("last_price", data.get("lastPrice", {}))
    if isinstance(last, dict):
        ltp = to_decimal(last.get("last_price", last.get("ltp", 0)))
    else:
        ltp = to_decimal(last)
    return Quote(
        symbol=symbol,
        ltp=ltp,
        open=to_decimal(data.get("ohlc", {}).get("open", 0)),
        high=to_decimal(data.get("ohlc", {}).get("high", 0)),
        low=to_decimal(data.get("ohlc", {}).get("low", 0)),
        close=to_decimal(data.get("ohlc", {}).get("close", 0)),
        volume=int(data.get("volume", 0)),
    )


def map_depth(symbol: str, data: dict) -> MarketDepth:
    depth_block = data.get("depth", {}) if isinstance(data.get("depth"), dict) else {}
    buy_levels = depth_block.get("buy", [])
    sell_levels = depth_block.get("sell", [])

    if buy_levels or sell_levels:
        bids = [
            DepthLevel(
                price=to_decimal(level.get("price", 0)),
                quantity=int(level.get("quantity") or 0),
                orders=int(level.get("orders") or 0),
            )
            for level in buy_levels[:20]
            if isinstance(level, dict)
        ]
        asks = [
            DepthLevel(
                price=to_decimal(level.get("price", 0)),
                quantity=int(level.get("quantity") or 0),
                orders=int(level.get("orders") or 0),
            )
            for level in sell_levels[:20]
            if isinstance(level, dict)
        ]
        return MarketDepth(symbol=symbol, bids=bids, asks=asks)

    bids = []
    asks = []
    for i in range(20):
        bid = (
            data.get(f"bid{i}") or data.get("bids", [None] * 20)[i]
            if i < len(data.get("bids", []))
            else None
        )
        ask = (
            data.get(f"ask{i}") or data.get("asks", [None] * 20)[i]
            if i < len(data.get("asks", []))
            else None
        )
        if bid and isinstance(bid, dict):
            bids.append(
                DepthLevel(
                    price=to_decimal(bid.get("price", 0)),
                    quantity=int(bid.get("quantity") or bid.get("orders") or 0),
                    orders=int(bid.get("orders") or 0),
                )
            )
        if ask and isinstance(ask, dict):
            asks.append(
                DepthLevel(
                    price=to_decimal(ask.get("price", 0)),
                    quantity=int(ask.get("quantity") or ask.get("orders") or 0),
                    orders=int(ask.get("orders") or 0),
                )
            )
    return MarketDepth(symbol=symbol, bids=bids, asks=asks)


def map_position(data: dict) -> Position:
    return Position(
        symbol=data.get("tradingSymbol", ""),
        exchange=_normalize_exchange(data.get("exchangeSegment", "")),
        quantity=int(data.get("netQty", 0)),
        product_type=_PRODUCT_MAP.get(
            data.get("productType", "INTRADAY"), ProductType.INTRADAY
        ),
        average_price=to_decimal(data.get("avgBuyCost", data.get("costPrice", 0))),
        realized_pnl=to_decimal(data.get("realizedProfit", 0)),
        unrealized_pnl=to_decimal(data.get("unrealizedProfit", 0)),
    )


def map_holding(data: dict) -> Holding:
    return Holding(
        symbol=data.get("tradingSymbol", ""),
        exchange=_normalize_exchange(data.get("exchangeSegment", "")),
        quantity=int(data.get("holdingQty", data.get("quantity", 0))),
        average_price=to_decimal(data.get("avgBuyPrice", data.get("costPrice", 0))),
        isin=data.get("isin", ""),
        t1_quantity=int(data.get("t1Qty", 0)),
    )


def map_balance(data: dict) -> Balance:
    return Balance(
        available_cash=to_decimal(
            data.get("availabelBalance", data.get("availableMargin", 0))
        ),
        utilized_margin=to_decimal(data.get("utilizedMargin", 0)),
        total_margin=to_decimal(data.get("totalMargin", 0)),
    )


def map_trade(data: dict) -> Trade:
    return Trade(
        trade_id=str(data.get("tradeId", data.get("orderId", ""))),
        order_id=str(data.get("orderId", "")),
        symbol=data.get("tradingSymbol", ""),
        exchange=_normalize_exchange(data.get("exchangeSegment", "")),
        side=_SIDE_MAP.get(data.get("transactionType", 1), Side.BUY),
        quantity=int(data.get("tradedQty", data.get("quantity", 0))),
        price=to_decimal(data.get("tradedPrice", data.get("price", 0))),
    )


def _normalize_exchange(segment: str) -> str:
    segment = str(segment).upper()
    return SEGMENT_TO_EXCHANGE.get(segment, segment)

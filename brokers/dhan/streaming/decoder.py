"""Dhan WebSocket message decoder — JSON ticks to domain events.

Parses incoming JSON messages from the Dhan market feed WebSocket into
``MarketTickEvent`` and ``OrderUpdateEvent`` domain events.

Dhan tick format (quote mode):
{
    "instrument_key": "NSE_EQ|1333",
    "type": "ltp" | "quote" | "depth",
    "ltp": 2500.50,
    "ltt": 1234567890,
    "open": 2490.0,
    "high": 2510.0,
    "low": 2480.0,
    "close": 2505.0,
    "volume": 100000,
    "best_bid_price": 2500.0,
    "best_ask_price": 2501.0,
    "best_bid_qty": 100,
    "best_ask_qty": 200,
    "depth": { "buy": [...], "sell": [...] }
}

Dhan order update format:
{
    "Type": "order_alert",
    "orderNo": "123456",
    "tradingSymbol": "RELIANCE",
    "exchangeSegment": "NSE_EQ",
    "orderStatus": "TRADED",
    "filledQty": 10,
    "avgTradePrice": 2500.50,
    ...
}
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from brokers.infrastructure.logging import get_logger
from brokers.infrastructure.streaming.stream_health import (
    MarketTickEvent,
    OrderUpdateEvent,
)

logger = get_logger(__name__)


def decode_market_message(raw: str | bytes) -> list[MarketTickEvent | OrderUpdateEvent]:
    """Decode a raw Dhan WS message into domain events.

    Handles both market data ticks and order updates in a single
    decoder function for the orchestrator's ``decode_fn`` callback.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.debug("dhan_decode_json_error", error=str(exc)[:100])
        return []

    # Batch format (list of ticks) — check BEFORE dict to avoid .get() on list
    if isinstance(data, list):
        return _parse_batch(data)

    # Single dict message
    if isinstance(data, dict):
        return _parse_single(data)

    return []


def _parse_batch(items: list) -> list[MarketTickEvent | OrderUpdateEvent]:
    """Parse a batch (list) of messages."""
    events: list[MarketTickEvent | OrderUpdateEvent] = []
    for item in items:
        if isinstance(item, dict):
            for event in _parse_single(item):
                events.append(event)
    return events


def _parse_single(data: dict[str, Any]) -> list[MarketTickEvent | OrderUpdateEvent]:
    """Parse a single dict message — order update or market tick."""
    # Order update
    if data.get("Type") == "order_alert":
        event = _parse_order_update(data)
        return [event] if event else []

    # Market data tick
    if "instrument_key" in data or "ltp" in data:
        tick = _parse_market_tick(data)
        return [tick] if tick else []

    return []


def _parse_market_tick(data: dict[str, Any]) -> MarketTickEvent | None:
    """Parse a single market tick JSON into a MarketTickEvent."""
    try:
        ltp = float(data.get("ltp", 0))
        if ltp <= 0:
            return None

        # Extract symbol from instrument_key or trading_symbol
        instrument_key = data.get("instrument_key", "")
        symbol = data.get("trading_symbol", instrument_key.split("|")[-1] if instrument_key else "")

        # Parse depth if available
        depth_bids: list[tuple[float, int]] = []
        depth_asks: list[tuple[float, int]] = []

        depth_data = data.get("depth")
        if isinstance(depth_data, dict):
            for level in depth_data.get("buy", []):
                if isinstance(level, dict):
                    price = float(level.get("price", 0))
                    qty_val = level.get("qty", level.get("quantity", 0)) or 0
                    qty = int(qty_val)
                    if price > 0 and qty > 0:
                        depth_bids.append((price, qty))

            for level in depth_data.get("sell", []):
                if isinstance(level, dict):
                    price = float(level.get("price", 0))
                    qty_val = level.get("qty", level.get("quantity", 0)) or 0
                    qty = int(qty_val)
                    if price > 0 and qty > 0:
                        depth_asks.append((price, qty))

        return MarketTickEvent(
            symbol=symbol,
            ltp=ltp,
            open=float(data.get("open", 0)),
            high=float(data.get("high", 0)),
            low=float(data.get("low", 0)),
            close=float(data.get("close", 0)),
            volume=int(data.get("volume", 0)),
            change=float(data.get("change", 0)),
            depth_bids=tuple(depth_bids),
            depth_asks=tuple(depth_asks),
            broker_id="dhan",
            timestamp=datetime.now(timezone.utc),
        )
    except (ValueError, TypeError) as exc:
        logger.debug("dhan_tick_parse_error", error=str(exc)[:100])
        return None


def _parse_order_update(data: dict[str, Any]) -> OrderUpdateEvent | None:
    """Parse an order alert JSON into an OrderUpdateEvent."""
    try:
        order_id = str(data.get("orderNo", data.get("orderId", "")))
        if not order_id:
            return None

        return OrderUpdateEvent(
            order_id=order_id,
            symbol=data.get("tradingSymbol", data.get("trading_symbol", "")),
            status=_normalize_status(data.get("orderStatus", "")),
            side=data.get("transactionType", data.get("side", "")),
            quantity=int(data.get("tradedQty", data.get("quantity", 0))),
            filled_quantity=int(data.get("filledQty", data.get("filled_qty", 0))),
            price=float(data.get("price", 0)),
            average_price=float(data.get("avgTradePrice", data.get("average_price", 0))),
            broker_id="dhan",
            raw=data,
            timestamp=datetime.now(timezone.utc),
        )
    except (ValueError, TypeError) as exc:
        logger.debug("dhan_order_parse_error", error=str(exc)[:100])
        return None


def _normalize_status(status: str) -> str:
    """Normalize Dhan order status to canonical form."""
    mapping = {
        "TRANSIT": "OPEN",
        "PENDING": "OPEN",
        "OPEN": "OPEN",
        "TRADED": "FILLED",
        "PART_TRADED": "PARTIALLY_FILLED",
        "EXPIRED": "EXPIRED",
        "REJECTED": "REJECTED",
        "CANCELLED": "CANCELLED",
        "MODIFIED": "OPEN",
    }
    return mapping.get(status.upper(), "UNKNOWN")


__all__ = ["decode_market_message"]

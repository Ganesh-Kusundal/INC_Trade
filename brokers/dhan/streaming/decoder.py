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


def decode_market_message(
    raw: str | bytes,
    symbol_lookup: Callable[[str], str] | None = None,
) -> list[MarketTickEvent | OrderUpdateEvent]:
    """Decode a raw Dhan WS message into domain events.

    Handles both market data ticks and order updates in a single
    decoder function for the orchestrator's ``decode_fn`` callback.

    ``symbol_lookup`` optionally maps a Dhan ``security_id`` (numeric id or
    ``segment|id`` instrument_key) to the user-facing symbol.  Dhan's market
    feed carries no ``trading_symbol``, so without it emitted ticks would be
    keyed by the numeric id.
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.debug("dhan_decode_json_error", error=str(exc)[:100])
        return []

    # Batch format (list of ticks) — check BEFORE dict to avoid .get() on list
    if isinstance(data, list):
        return _parse_batch(data, symbol_lookup)

    # Single dict message
    if isinstance(data, dict):
        return _parse_single(data, symbol_lookup)

    return []


def _parse_batch(
    items: list, symbol_lookup: Callable[[str], str] | None = None
) -> list[MarketTickEvent | OrderUpdateEvent]:
    """Parse a batch (list) of messages."""
    events: list[MarketTickEvent | OrderUpdateEvent] = []
    for item in items:
        if isinstance(item, dict):
            for event in _parse_single(item, symbol_lookup):
                events.append(event)
    return events


def _parse_single(
    data: dict[str, Any], symbol_lookup: Callable[[str], str] | None = None
) -> list[MarketTickEvent | OrderUpdateEvent]:
    """Parse a single dict message — order update or market tick."""
    # Order update
    if data.get("Type") == "order_alert":
        event = _parse_order_update(data)
        return [event] if event else []

    # Market data tick
    if "instrument_key" in data or "ltp" in data:
        tick = _parse_market_tick(data, symbol_lookup)
        return [tick] if tick else []

    return []


def _parse_market_tick(
    data: dict[str, Any],
    symbol_lookup: Callable[[str], str] | None = None,
) -> MarketTickEvent | None:
    """Parse a single market tick JSON into a MarketTickEvent."""
    try:
        ltp = float(data.get("ltp", 0))
        if ltp <= 0:
            return None

        # Dhan's market feed has no trading_symbol field.  Map the numeric
        # security_id / instrument_key back to the user-facing symbol via the
        # feed's subscription map when available, so emitted Quote.symbol
        # matches what the user subscribed with (consistent with depth_feed).
        instrument_key = data.get("instrument_key", "")
        security_id = instrument_key.split("|")[-1] if instrument_key else ""
        if symbol_lookup is not None and security_id:
            symbol = symbol_lookup(security_id) or security_id
        else:
            symbol = data.get("trading_symbol", security_id)

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


from brokers.dhan.status_mapping import normalize_status as _normalize_status


__all__ = ["decode_market_message"]

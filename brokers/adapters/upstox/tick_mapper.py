"""Map Upstox WS feed frames to domain Quote."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from brokers.domain import Quote
from brokers.utils.price import to_decimal


def frame_to_quote(frame: dict[str, Any]) -> Quote | None:
    if not isinstance(frame, dict):
        return None
    ltp_raw = frame.get("ltp", frame.get("last_price"))
    if ltp_raw is None:
        return None
    ohlc = frame.get("ohlc") or {}
    return Quote(
        symbol=str(frame.get("symbol", "")),
        exchange=str(frame.get("exchange", "")),
        ltp=to_decimal(ltp_raw),
        open=to_decimal(ohlc.get("open", 0)),
        high=to_decimal(ohlc.get("high", 0)),
        low=to_decimal(ohlc.get("low", 0)),
        close=to_decimal(frame.get("close", ohlc.get("close", 0))),
        volume=int(frame.get("volume", 0)),
    )


def frame_to_tick_dict(frame: dict[str, Any]) -> dict[str, Any] | None:
    """Legacy dict tick for callers expecting mapping shape."""
    quote = frame_to_quote(frame)
    if quote is None:
        return None
    return {
        "symbol": quote.symbol,
        "exchange": quote.exchange,
        "ltp": quote.ltp,
        "volume": quote.volume,
        "timestamp": frame.get("timestamp", ""),
        "open": quote.open,
        "high": quote.high,
        "low": quote.low,
        "close": quote.close,
        "raw": frame,
    }

"""Upstox V3 protobuf decoder — binary frames to domain events.

Decodes binary FeedResponse frames from the Upstox V3 market data WebSocket
into ``MarketTickEvent`` domain events.

Protocol flow:
1. Receive binary frame from WebSocket
2. Decompress gzip if needed
3. Parse as protobuf ``FeedResponse``
4. Extract per-instrument feed data (LTPC, Quote, FullFeed)
5. Convert to ``MarketTickEvent`` objects
"""

from __future__ import annotations

import gzip
import struct
from datetime import datetime, timezone
from typing import Any

from brokers.infrastructure.logging import get_logger
from brokers.infrastructure.streaming.stream_health import (
    MarketTickEvent,
)

logger = get_logger(__name__)

# Try to import protobuf — graceful fallback if not available
try:
    from brokers.upstox.streaming.proto.market_feed_pb2 import FeedResponse
    _PROTO_AVAILABLE = True
except ImportError:
    try:
        from brokers.upstox.streaming.proto.MarketDataFeed_pb2 import FeedResponse  # type: ignore[attr-defined]
        _PROTO_AVAILABLE = True
    except ImportError:
        _PROTO_AVAILABLE = False
        logger.warning("upstox_protobuf_not_available")


def decode_market_message(
    raw: str | bytes,
) -> list[MarketTickEvent]:
    """Decode a raw Upstox V3 WS message into MarketTickEvents.

    Handles both binary protobuf frames and JSON control messages.
    """
    if isinstance(raw, str):
        # JSON control message (market_info, etc.) — not a tick
        return []

    if not isinstance(raw, bytes) or len(raw) == 0:
        return []

    if not _PROTO_AVAILABLE:
        return []

    # Try to decompress gzip
    data = _maybe_decompress(raw)

    # Parse protobuf FeedResponse
    try:
        response = FeedResponse()
        response.ParseFromString(data)
    except Exception as exc:
        # Try V2 format fallback (type-prefix + length + payload)
        events = _try_v2_fallback(data)
        if events:
            return events
        logger.debug("upstox_decode_error", error=str(exc)[:100])
        return []

    return _extract_ticks(response)


def _maybe_decompress(data: bytes) -> bytes:
    """Decompress gzip if the data is gzip-compressed."""
    # Gzip magic number: 1f 8b
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        try:
            return gzip.decompress(data)
        except Exception:
            return data
    return data


def _try_v2_fallback(data: bytes) -> list[MarketTickEvent]:
    """Try to parse as V2 format: 1-byte type + 2-byte length + protobuf payload."""
    if len(data) < 3:
        return []

    try:
        data[0]
        msg_len = struct.unpack(">H", data[1:3])[0]
        if 3 + msg_len > len(data):
            return []

        payload = data[3:3 + msg_len]
        response = FeedResponse()
        response.ParseFromString(payload)
        return _extract_ticks(response)
    except Exception:
        return []


def _extract_ticks(response: Any) -> list[MarketTickEvent]:
    """Extract MarketTickEvents from a parsed FeedResponse."""
    events: list[MarketTickEvent] = []
    now = datetime.now(timezone.utc)

    feeds = getattr(response, "feeds", None)
    if feeds is None:
        return events

    for instrument_key, feed in feeds.items():
        tick = _feed_to_tick(instrument_key, feed, now)
        if tick is not None:
            events.append(tick)

    return events


def _feed_to_tick(
    instrument_key: str,
    feed: Any,
    timestamp: datetime,
) -> MarketTickEvent | None:
    """Convert a single Feed protobuf to a MarketTickEvent."""
    try:
        # Extract the feed union field
        # FeedResponse.Feed can be: ltpc, fullFeed, firstLevelWithGreeks
        ltp = 0.0
        open_price = 0.0
        high = 0.0
        low = 0.0
        close = 0.0
        volume = 0
        depth_bids: list[tuple[float, int]] = []
        depth_asks: list[tuple[float, int]] = []

        # Try ltpc field
        ltpc = getattr(feed, "ltpc", None)
        if ltpc is not None:
            ltp = float(getattr(ltpc, "ltp", 0))
            close = float(getattr(ltpc, "cp", 0))

        # Try fullFeed field
        full_feed = getattr(feed, "fullFeed", None)
        if full_feed is not None:
            # MarketFullFeed
            market_ff = getattr(full_feed, "marketFF", None)
            if market_ff is not None:
                ltpc_data = getattr(market_ff, "ltpc", None)
                if ltpc_data is not None:
                    ltp = float(getattr(ltpc_data, "ltp", 0))
                    close = float(getattr(ltpc_data, "cp", 0))

                ohlc = getattr(market_ff, "ohlc", None)
                if ohlc is not None:
                    open_price = float(getattr(ohlc, "open", 0))
                    high = float(getattr(ohlc, "high", 0))
                    low = float(getattr(ohlc, "low", 0))
                    close = float(getattr(ohlc, "close", 0))

                # Market depth
                market_depth = getattr(market_ff, "marketDepth", None)
                if market_depth is not None:
                    depth_bids, depth_asks = _parse_depth(market_depth)

                # Volume
                market_ohlc = getattr(market_ff, "ohlc", None)
                if market_ohlc is not None:
                    volume = int(getattr(market_ohlc, "vol", 0))

            # IndexFullFeed
            index_ff = getattr(full_feed, "indexFF", None)
            if index_ff is not None:
                ltpc_data = getattr(index_ff, "ltpc", None)
                if ltpc_data is not None:
                    ltp = float(getattr(ltpc_data, "ltp", 0))
                    close = float(getattr(ltpc_data, "cp", 0))

                ohlc = getattr(index_ff, "ohlc", None)
                if ohlc is not None:
                    open_price = float(getattr(ohlc, "open", 0))
                    high = float(getattr(ohlc, "high", 0))
                    low = float(getattr(ohlc, "low", 0))
                    close = float(getattr(ohlc, "close", 0))

        # Try firstLevelWithGreeks field
        flwg = getattr(feed, "firstLevelWithGreeks", None)
        if flwg is not None:
            ltpc_data = getattr(flwg, "ltpc", None)
            if ltpc_data is not None:
                ltp = float(getattr(ltpc_data, "ltp", 0))
                close = float(getattr(ltpc_data, "cp", 0))

        if ltp <= 0:
            return None

        # Extract symbol from instrument_key (e.g., "NSE_EQ|INE002A01018")
        symbol = instrument_key.split("|")[-1] if "|" in instrument_key else instrument_key

        return MarketTickEvent(
            symbol=symbol,
            ltp=ltp,
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
            depth_bids=tuple(depth_bids),
            depth_asks=tuple(depth_asks),
            broker_id="upstox",
            timestamp=timestamp,
        )
    except Exception as exc:
        logger.debug("upstox_feed_parse_error", error=str(exc)[:100])
        return None


def _parse_depth(market_depth: Any) -> tuple[list[tuple[float, int]], list[tuple[float, int]]]:
    """Parse market depth protobuf into bid/ask tuples."""
    bids: list[tuple[float, int]] = []
    asks: list[tuple[float, int]] = []

    # market_depth is a repeated DepthLevel message
    for i, level in enumerate(market_depth):
        price = float(getattr(level, "price", 0))
        qty = int(getattr(level, "quantity", 0))
        if price > 0 and qty > 0:
            if i < len(market_depth) // 2:
                bids.append((price, qty))
            else:
                asks.append((price, qty))

    return bids, asks


__all__ = ["decode_market_message"]

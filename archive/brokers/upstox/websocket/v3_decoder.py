"""Upstox V3 binary frame decoder.

The V3 server pushes Protobuf-encoded binary FeedResponse frames directly.

Mirrors Trade_J ``UpstoxBinaryParser`` / ``UpstoxMarketInfoParser``.
"""

from __future__ import annotations

import struct
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

FRAME_HEARTBEAT = 100
FRAME_TYPE_INDEX = 1
FRAME_TYPE_LIVE_FEED = 2

# Thread-safe decode-failure counter for observability.
# Incremented whenever both V3 and V2 fallback decoding fail.
# Protected by _decode_lock for safe concurrent access from multiple
# WebSocket connections or threads.
_decode_failures: int = 0
_decode_lock: threading.Lock = threading.Lock()


def decode_failure_count() -> int:
    """Return the total number of frames that could not be decoded.

    A non-zero value visible on /healthz indicates a protocol mismatch,
    corrupt feed, or version skew that warrants investigation.
    """
    with _decode_lock:
        return _decode_failures


@dataclass
class ParsedFeedFrame:
    type: int
    raw: bytes
    payload: dict[str, Any] = field(default_factory=dict)


class UpstoxV3Decoder:
    """Parse Upstox V3 binary feed frames into plain dicts."""

    def parse(self, raw: bytes) -> list[ParsedFeedFrame] | ParsedFeedFrame | None:
        if not raw:
            return None

        # 1. Try parsing as FeedResponse (V3 WebSocket protocol)
        try:
            from .proto.market_feed_pb2 import FeedResponse

            response = FeedResponse()
            response.ParseFromString(raw)

            frames = []
            frame_type = response.type
            for key, feed in response.feeds.items():
                payload = self._feed_to_dict_v3(feed, key)
                frames.append(ParsedFeedFrame(type=frame_type, raw=raw, payload=payload))
            return frames
        except (ImportError, AttributeError, ValueError, TypeError) as e:
            # V3 protobuf decode failed — log and try V2 fallback.
            # We catch only expected protocol-level exceptions so that
            # genuine bugs (e.g. MemoryError, KeyboardInterrupt) propagate.
            logger.warning(
                "Upstox V3 protobuf decode failed, falling back to V2: %s: %s",
                type(e).__name__,
                e,
            )
            # Fall back to V2/mock 1-byte type prefix + 2-byte length parsing
            try:
                if len(raw) < 3:
                    self._record_decode_failure()
                    return None
                frame_type = raw[0]
                (length,) = struct.unpack(">H", raw[1:3])
                if len(raw) < 3 + length:
                    self._record_decode_failure()
                    return None
                payload_bytes = bytes(raw[3 : 3 + length])
                if frame_type == FRAME_HEARTBEAT:
                    return ParsedFeedFrame(type=frame_type, raw=raw, payload={})

                from .proto.market_feed_pb2 import Feed
                feed = Feed()
                feed.ParseFromString(payload_bytes)
                payload = self._feed_to_dict_old(feed)
                return ParsedFeedFrame(type=frame_type, raw=raw, payload=payload)
            except (ImportError, AttributeError, ValueError, struct.error, TypeError) as exc:
                self._record_decode_failure()
                logger.error(
                    "Upstox V3 fallback decode failed: %s: %s",
                    type(exc).__name__,
                    exc,
                )
                return None

    @staticmethod
    def _record_decode_failure() -> None:
        """Thread-safe increment of the decode-failure counter."""
        with _decode_lock:
            global _decode_failures
            _decode_failures += 1

    @staticmethod
    def _feed_to_dict_v3(feed: Any, instrument_key: str) -> dict[str, Any]:
        out: dict[str, Any] = {
            "instrument_key": instrument_key,
        }

        # Determine populated Oneof field
        union_field = feed.WhichOneof("FeedUnion")
        if union_field == "ltpc":
            lt = feed.ltpc
            out["ltp"] = lt.ltp
            out["exchange_timestamp"] = lt.ltt
            out["volume"] = lt.ltq
            out["close_price"] = lt.cp
        elif union_field == "firstLevelWithGreeks":
            flg = feed.firstLevelWithGreeks
            if flg.HasField("ltpc"):
                out["ltp"] = flg.ltpc.ltp
                out["exchange_timestamp"] = flg.ltpc.ltt
                out["volume"] = flg.vtt
                out["close_price"] = flg.ltpc.cp
            if flg.HasField("firstDepth"):
                out["best_bid_price"] = flg.firstDepth.bidP
                out["best_ask_price"] = flg.firstDepth.askP
            out["vtt"] = flg.vtt
            out["oi"] = flg.oi
            out["iv"] = flg.iv
        elif union_field == "fullFeed":
            ff = feed.fullFeed
            union_ff = ff.WhichOneof("FullFeedUnion")
            if union_ff == "marketFF":
                mf = ff.marketFF
                if mf.HasField("ltpc"):
                    out["ltp"] = mf.ltpc.ltp
                    out["exchange_timestamp"] = mf.ltpc.ltt
                    out["volume"] = mf.vtt
                    out["close_price"] = mf.ltpc.cp
                out["atp"] = mf.atp
                out["vtt"] = mf.vtt
                out["oi"] = mf.oi
                out["iv"] = mf.iv
                out["total_buy_quantity"] = mf.tbq
                out["total_sell_quantity"] = mf.tsq

                # Best bid/ask from market depth
                if mf.marketLevel.bidAskQuote:
                    out["best_bid_price"] = mf.marketLevel.bidAskQuote[0].bidP
                    out["best_ask_price"] = mf.marketLevel.bidAskQuote[0].askP
                    out["depth"] = {
                        "bids": [{"price": b.bidP, "quantity": b.bidQ} for b in mf.marketLevel.bidAskQuote if b.bidP > 0],
                        "asks": [{"price": b.askP, "quantity": b.askQ} for b in mf.marketLevel.bidAskQuote if b.askP > 0]
                    }

                if mf.marketOHLC.ohlc:
                    out["ohlc"] = {
                        "open": mf.marketOHLC.ohlc[0].open,
                        "high": mf.marketOHLC.ohlc[0].high,
                        "low": mf.marketOHLC.ohlc[0].low,
                        "close": mf.marketOHLC.ohlc[0].close
                    }
            elif union_ff == "indexFF":
                inf = ff.indexFF
                if inf.HasField("ltpc"):
                    out["ltp"] = inf.ltpc.ltp
                    out["exchange_timestamp"] = inf.ltpc.ltt
                    out["close_price"] = inf.ltpc.cp
                if inf.marketOHLC.ohlc:
                    out["ohlc"] = {
                        "open": inf.marketOHLC.ohlc[0].open,
                        "high": inf.marketOHLC.ohlc[0].high,
                        "low": inf.marketOHLC.ohlc[0].low,
                        "close": inf.marketOHLC.ohlc[0].close
                    }
        return out

    @staticmethod
    def _feed_to_dict_old(feed: Any) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if feed.HasField("ltpc"):
            lt = feed.ltpc
            out["ltpc"] = {"ltp": lt.ltp, "ltt": lt.ltt, "ltq": lt.ltq, "cp": lt.cp}
        if feed.HasField("first_level_with_greeks"):
            flg = feed.first_level_with_greeks
            out["first_level_with_greeks"] = {
                "ltpc": {"ltp": flg.ltpc.ltp, "ltq": flg.ltpc.ltq, "cp": flg.ltpc.cp},
                "first_depth": {
                    "bidQ": flg.firstDepth.bidQ,
                    "bidP": flg.firstDepth.bidP,
                    "askQ": flg.firstDepth.askQ,
                    "askP": flg.firstDepth.askP,
                },
                "vtt": flg.vtt,
                "oi": flg.oi,
                "iv": flg.iv,
                "optionGreeks": {
                    "delta": flg.optionGreeks.delta,
                    "theta": flg.optionGreeks.theta,
                    "gamma": flg.optionGreeks.gamma,
                    "vega": flg.optionGreeks.vega,
                    "rho": flg.optionGreeks.rho,
                },
            }
        if feed.HasField("fullFeed"):
            ff = feed.fullFeed
            if ff.HasField("marketFF"):
                mf = ff.marketFF
                out["full_feed"] = {
                    "ltpc": {
                        "ltp": mf.ltpc.ltp,
                        "cp": mf.ltpc.cp,
                        "ltt": mf.ltpc.ltt,
                        "ltq": mf.ltpc.ltq,
                    },
                    "atp": mf.atp,
                    "vtt": mf.vtt,
                    "oi": mf.oi,
                    "iv": mf.iv,
                    "tbq": mf.tbq,
                    "tsq": mf.tsq,
                    "optionGreeks": {
                        "delta": mf.optionGreeks.delta,
                        "theta": mf.optionGreeks.theta,
                        "gamma": mf.optionGreeks.gamma,
                        "vega": mf.optionGreeks.vega,
                        "rho": mf.optionGreeks.rho,
                    },
                    "marketOHLC": [
                        {
                            "interval": o.interval,
                            "open": o.open,
                            "high": o.high,
                            "low": o.low,
                            "close": o.close,
                            "vol": o.vol,
                            "ts": o.ts,
                        }
                        for o in mf.marketOHLC.ohlc
                    ],
                    "marketLevel": {
                        "bidAskQuote": [
                            {
                                "bidQ": b.bidQ,
                                "bidP": b.bidP,
                                "askQ": b.askQ,
                                "askP": b.askP,
                            }
                            for b in mf.marketLevel.bidAskQuote
                        ]
                    },
                }
        if feed.HasField("indexFeed"):
            idx = feed.indexFeed
            out["index_feed"] = {
                "ltpc": {"ltp": idx.ltpc.ltp, "cp": idx.ltpc.cp},
                "marketOHLC": [
                    {
                        "interval": o.interval,
                        "open": o.open,
                        "high": o.high,
                        "low": o.low,
                        "close": o.close,
                        "vol": o.vol,
                        "ts": o.ts,
                    }
                    for o in idx.marketOHLC.ohlc
                ],
            }
        return out

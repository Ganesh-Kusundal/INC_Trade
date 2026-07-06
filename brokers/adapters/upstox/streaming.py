"""Upstox streaming adapter — real-time market data via WebSocket (Protobuf V3).

Uses sync threading (websocket-client library) for the WebSocket connection.
Obtains authorized WS URL via UpstoxFeedAuthorizer before each connect/reconnect.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import websocket

from brokers.adapters.base_streaming import BaseWebSocketStreaming
from brokers.adapters.upstox.config import SEGMENT_TO_EXCHANGE
from brokers.adapters.upstox.feed_authorizer import UpstoxFeedAuthorizer
from brokers.adapters.upstox.instruments import UpstoxInstruments, resolve_upstox_instrument_key
from brokers.adapters.upstox.tick_mapper import frame_to_quote, frame_to_tick_dict
from brokers.config.endpoints import Upstox
from brokers.domain.constants.timeouts import DEFAULT_MAX_RECONNECT_DELAY, DEFAULT_RECONNECT_DELAY

logger = logging.getLogger(__name__)

FALLBACK_WS_URL = Upstox.WS_FALLBACK


class UpstoxV3Decoder:
    """Parse Upstox V3 binary feed frames into dicts."""

    def parse(self, raw: bytes) -> list[dict[str, Any]] | None:
        if not raw:
            return None
        try:
            from brokers.adapters.upstox.proto.market_feed_pb2 import FeedResponse

            response = FeedResponse()
            response.ParseFromString(raw)

            frames = []
            for key, feed in response.feeds.items():
                payload = self._feed_to_dict_v3(feed, key)
                frames.append(payload)
            return frames
        except Exception as exc:
            logger.warning("Upstox V3 protobuf decode failed: %s", exc)
            return None

    @staticmethod
    def _feed_to_dict_v3(feed: Any, instrument_key: str) -> dict[str, Any]:
        parts = instrument_key.split("|")
        symbol = parts[1] if len(parts) > 1 else instrument_key
        exchange = SEGMENT_TO_EXCHANGE.get(parts[0], "") if len(parts) > 0 else ""

        out: dict[str, Any] = {
            "symbol": symbol,
            "exchange": exchange,
            "instrument_key": instrument_key,
        }

        union_field = feed.WhichOneof("FeedUnion")
        if union_field == "ltpc":
            lt = feed.ltpc
            out["ltp"] = lt.ltp
            out["timestamp"] = lt.ltt
            out["volume"] = lt.ltq
            out["close"] = lt.cp
        elif union_field == "firstLevelWithGreeks":
            flg = feed.firstLevelWithGreeks
            if flg.HasField("ltpc"):
                out["ltp"] = flg.ltpc.ltp
                out["timestamp"] = flg.ltpc.ltt
                out["volume"] = flg.vtt
                out["close"] = flg.ltpc.cp
            out["oi"] = flg.oi
            out["iv"] = flg.iv
        elif union_field == "fullFeed":
            ff = feed.fullFeed
            union_ff = ff.WhichOneof("FullFeedUnion")
            if union_ff == "marketFF":
                mf = ff.marketFF
                if mf.HasField("ltpc"):
                    out["ltp"] = mf.ltpc.ltp
                    out["timestamp"] = mf.ltpc.ltt
                    out["volume"] = mf.vtt
                    out["close"] = mf.ltpc.cp
                out["oi"] = mf.oi
                out["iv"] = mf.iv

                if mf.marketLevel.bidAskQuote:
                    out["depth"] = {
                        "bids": [
                            {"price": b.bidP, "quantity": b.bidQ}
                            for b in mf.marketLevel.bidAskQuote
                            if b.bidP > 0
                        ],
                        "asks": [
                            {"price": b.askP, "quantity": b.askQ}
                            for b in mf.marketLevel.bidAskQuote
                            if b.askP > 0
                        ],
                    }
                if mf.marketOHLC.ohlc:
                    out["ohlc"] = {
                        "open": mf.marketOHLC.ohlc[0].open,
                        "high": mf.marketOHLC.ohlc[0].high,
                        "low": mf.marketOHLC.ohlc[0].low,
                        "close": mf.marketOHLC.ohlc[0].close,
                    }
        return out


class UpstoxStreaming(BaseWebSocketStreaming):
    """Real-time market data streaming via Upstox WebSocket (Protobuf)."""

    def __init__(
        self,
        access_token: str | Callable[[], str],
        feed_authorizer: UpstoxFeedAuthorizer | None = None,
        instruments: UpstoxInstruments | None = None,
        ws_url: str = FALLBACK_WS_URL,
        reconnect_delay: float = DEFAULT_RECONNECT_DELAY,
        max_reconnect_delay: float = DEFAULT_MAX_RECONNECT_DELAY,
        mode: str = "ltpc",
    ):
        super().__init__(
            ws_url=ws_url,
            reconnect_delay=reconnect_delay,
            max_reconnect_delay=max_reconnect_delay,
            log_prefix="upstox_ws",
        )
        if callable(access_token):
            self._token_provider: Callable[[], str] = access_token
        else:
            self._token_provider = lambda: access_token
        self._feed_authorizer = feed_authorizer
        self._instruments = instruments
        self._mode = mode
        self._decoder = UpstoxV3Decoder()
        self._on_depth: Callable[[Any], None] | None = None
        self._url_lock = threading.Lock()
        self._authorized_url: str = ""

    def update_access_token(self, token: str) -> None:
        """Called when bearer token is refreshed — next connect uses new token."""
        self._token_provider = lambda: token

    @property
    def mode(self) -> str:
        return self._mode

    @mode.setter
    def mode(self, val: str) -> None:
        self._mode = val

    @property
    def on_depth(self) -> Callable[[Any], None] | None:
        return self._on_depth

    @on_depth.setter
    def on_depth(self, callback: Callable[[Any], None] | None) -> None:
        self._on_depth = callback

    def _resolve_key(self, symbol: str, exchange: str) -> str:
        return resolve_upstox_instrument_key(symbol, exchange, self._instruments)

    def subscribe(self, symbol: str, exchange: str = "NSE") -> None:
        key = self._resolve_key(symbol, exchange)
        super().subscribe(key)

    def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None:
        key = self._resolve_key(symbol, exchange)
        super().unsubscribe(key)

    def _resolve_ws_url(self) -> str:
        if self._feed_authorizer is None:
            return self._ws_url
        try:
            url = self._feed_authorizer.authorize_market_data_v3()
            if url:
                with self._url_lock:
                    self._authorized_url = url
                return url
        except Exception as exc:
            logger.warning("Upstox feed authorize failed, using fallback URL: %s", exc)
        return self._ws_url

    def _get_ws_url(self) -> str:
        return self._resolve_ws_url()

    def _get_ws_headers(self) -> dict[str, str]:
        # Authorized feed URL embeds credentials; extra Bearer header is unnecessary.
        return {}

    def _build_subscribe_message(self, keys: list[str]) -> str:
        return json.dumps(
            {
                "guid": "",
                "method": "sub",
                "data": {
                    "mode": self._mode,
                    "instrumentKeys": keys,
                },
            },
            separators=(",", ":"),
        )

    def _build_unsubscribe_message(self, keys: list[str]) -> str:
        return json.dumps(
            {
                "guid": "",
                "method": "unsub",
                "data": {
                    "instrumentKeys": keys,
                },
            },
            separators=(",", ":"),
        )

    def _send_ws_binary(self, payload: str) -> None:
        if not self._ws:
            return
        data = payload.encode("utf-8")
        send_binary = getattr(self._ws, "send_binary", None)
        if callable(send_binary):
            send_binary(data)
            return
        self._ws.send(data, opcode=websocket.ABNF.OPCODE_BINARY)

    def _send_subscribe(self, keys: list[str]) -> None:
        self._send_ws_binary(self._build_subscribe_message(keys))

    def _send_unsubscribe(self, keys: list[str]) -> None:
        self._send_ws_binary(self._build_unsubscribe_message(keys))

    def _on_message(self, ws: Any, message: str | bytes) -> None:
        if isinstance(message, bytes):
            frames = self._decoder.parse(message)
            if frames:
                for frame in frames:
                    quote = frame_to_quote(frame)
                    tick = frame_to_tick_dict(frame) if quote is None else quote
                    if tick and self._on_tick:
                        self._on_tick(tick)  # type: ignore[arg-type]

                    if quote and "depth" in frame and self._on_depth:
                        from brokers.domain import DepthLevel, MarketDepth

                        depth_data = frame["depth"]
                        bids = [
                            DepthLevel(
                                price=Decimal(str(b["price"])),
                                quantity=int(b["quantity"]),
                            )
                            for b in depth_data.get("bids", [])
                        ]
                        asks = [
                            DepthLevel(
                                price=Decimal(str(a["price"])),
                                quantity=int(a["quantity"]),
                            )
                            for a in depth_data.get("asks", [])
                        ]
                        depth_obj = MarketDepth(
                            symbol=quote.symbol, bids=bids, asks=asks
                        )
                        self._on_depth(depth_obj)
        else:
            try:
                data = json.loads(message)
                if data.get("type") == "market_info":
                    logger.info("Upstox WS market info received")
            except Exception:
                pass


"""Dhan streaming adapter — real-time market data via WebSocket.

Uses sync threading (websocket-client library) for the WebSocket connection.
Runs the WebSocket in a background daemon thread.
"""

from __future__ import annotations

import json
import logging
import struct
from collections.abc import Callable
from decimal import Decimal

from brokers_core.adapters.base_streaming import BaseWebSocketStreaming
from brokers_core.adapters.dhan.config import SEGMENT_TO_EXCHANGE
from brokers_core.adapters.dhan.identity import DhanInstrumentResolver
from brokers_core.adapters.dhan.segments import resolve_segment
from brokers_core.config.endpoints import Dhan
from brokers_core.domain.constants.timeouts import DEFAULT_MAX_RECONNECT_DELAY, DEFAULT_RECONNECT_DELAY

logger = logging.getLogger(__name__)

WS_URL = Dhan.WS_FEED

# Dhan v2 WebSocket subscribe request codes (dhanhq MarketFeed constants).
MODE_SUBSCRIBE_CODE: dict[str, int] = {"LTP": 15, "QUOTE": 17, "FULL": 21}
MODE_UNSUBSCRIBE_CODE: dict[str, int] = {"LTP": 16, "QUOTE": 18, "FULL": 22}


class DhanStreaming(BaseWebSocketStreaming):
    """Real-time market data streaming via Dhan WebSocket.

    Args:
        access_token: Static access token string, or callable returning current token.
        client_id: Dhan client ID.
        resolver: DhanInstrumentResolver instance to map symbol <-> security_id.
        ws_url: WebSocket URL (default: production).
        reconnect_delay: Initial reconnect delay in seconds.
        max_reconnect_delay: Maximum reconnect delay in seconds.

    Usage::

        streaming = DhanStreaming(access_token="...", client_id="...", resolver=resolver)
        streaming.on_tick = lambda tick: print(tick)
        streaming.subscribe("RELIANCE", "NSE")
        streaming.start()
        # ... later
        streaming.stop()
    """

    def __init__(
        self,
        access_token: str | Callable[[], str],
        client_id: str,
        resolver: DhanInstrumentResolver | None = None,
        ws_url: str = WS_URL,
        reconnect_delay: float = DEFAULT_RECONNECT_DELAY,
        max_reconnect_delay: float = DEFAULT_MAX_RECONNECT_DELAY,
    ):
        super().__init__(
            ws_url=ws_url,
            reconnect_delay=reconnect_delay,
            max_reconnect_delay=max_reconnect_delay,
            log_prefix="dhan_ws",
        )
        self._access_token = access_token
        self._client_id = client_id
        self._resolver = resolver
        self._feed_mode = "QUOTE"

    def set_mode(self, mode: str) -> None:
        """Set subscription packet mode: LTP, QUOTE, or FULL."""
        self._feed_mode = mode.strip().upper()

    @property
    def feed_mode(self) -> str:
        return self._feed_mode

    def subscribe(self, symbol: str, exchange: str = "NSE") -> None:
        try:
            ref = self._resolver.resolve(symbol, exchange)
            key = f"{ref.exchange_segment}|{ref.security_id}"
            super().subscribe(key)
            logger.info("subscribed", extra={"symbol": symbol, "exchange": exchange, "key": key})
        except Exception as e:
            logger.error(
                "failed_to_subscribe", extra={"symbol": symbol, "exchange": exchange, "error": str(e)}
            )
            segment = resolve_segment(exchange)
            key = f"{segment}|{symbol}"
            super().subscribe(key)

    def register_tick_handler(
        self, symbol: str, exchange: str, handler: Callable[[dict], None]
    ) -> str:
        """Register a callback for ticks on a specific symbol without clobbering on_tick."""
        ref = self._resolver.resolve(symbol, exchange)
        key = f"{ref.exchange_segment}|{ref.security_id}"
        self.register_tick_handler_for_key(key, handler)
        return key

    def register_tick_handler_for_key(
        self, key: str, handler: Callable[[dict], None]
    ) -> None:
        super().register_tick_handler(key, handler)

    def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None:
        try:
            ref = self._resolver.resolve(symbol, exchange)
            if ref:
                key = f"{ref.exchange_segment}|{ref.security_id}"
                super().unsubscribe(key)
                logger.info("unsubscribed", extra={"symbol": symbol, "exchange": exchange, "key": key})
        except Exception as e:
            logger.error(
                "failed_to_unsubscribe", extra={"symbol": symbol, "exchange": exchange, "error": str(e)}
            )
            segment = resolve_segment(exchange)
            key = f"{segment}|{symbol}"
            super().unsubscribe(key)

    def update_token(self, new_token: str) -> None:
        """Update the access token (for broadcast system compatibility).

        Args:
            new_token: The new access token.
        """
        self._access_token = new_token

    def _get_access_token(self) -> str:
        """Get the current access token, calling the function if needed."""
        if callable(self._access_token):
            return self._access_token()
        return self._access_token

    def _get_ws_url(self) -> str:
        """Build the authenticated version 2 WebSocket URL."""
        token = self._get_access_token()
        return f"{self._ws_url}?version=2&token={token}&clientId={self._client_id}&authType=2"

    def _get_ws_headers(self) -> dict[str, str]:
        # Version 2 uses query parameters for auth, no headers needed
        return {}

    def _build_subscribe_message(self, keys: list[str]) -> str:
        instrument_list = []
        for key in keys:
            parts = key.split("|")
            if len(parts) == 2:
                instrument_list.append(
                    {"ExchangeSegment": parts[0], "SecurityId": parts[1]}
                )
        request_code = MODE_SUBSCRIBE_CODE.get(self._feed_mode, 17)
        return json.dumps(
            {
                "RequestCode": request_code,
                "InstrumentCount": len(instrument_list),
                "InstrumentList": instrument_list,
            }
        )

    def _build_unsubscribe_message(self, keys: list[str]) -> str:
        instrument_list = []
        for key in keys:
            parts = key.split("|")
            if len(parts) == 2:
                instrument_list.append(
                    {"ExchangeSegment": parts[0], "SecurityId": parts[1]}
                )
        request_code = MODE_UNSUBSCRIBE_CODE.get(self._feed_mode, 18)
        return json.dumps(
            {
                "RequestCode": request_code,
                "InstrumentCount": len(instrument_list),
                "InstrumentList": instrument_list,
            }
        )

    def _on_message(self, ws, message: str | bytes) -> None:
        """Override base _on_message to handle binary feed packets."""
        if isinstance(message, bytes):
            try:
                tick = self._parse_binary_message(message)
                if tick:
                    sid = tick.get("raw", {}).get("security_id")
                    ref = self._resolver.get_by_security_id(str(sid)) if sid else None
                    if ref:
                        tick["subscription_key"] = f"{ref.exchange_segment}|{ref.security_id}"
                    self._dispatch_tick(
                        tick, tick.get("subscription_key")
                    )
            except Exception as e:
                logger.warning("failed_to_parse_binary_tick", extra={"error": str(e)}, exc_info=True)
        else:
            super()._on_message(ws, message)

    def _parse_binary_message(self, message: bytes) -> dict | None:
        """Parse Dhan binary feed data."""
        if len(message) < 4:
            return None

        feed_code = message[0]

        if feed_code == 2:  # Ticker Data
            if len(message) < 16:
                return None
            unpacked = struct.unpack("<BHBIfI", message[:16])
            security_id = unpacked[3]
            ltp = unpacked[4]
            timestamp = unpacked[5]

            ref = self._resolver.get_by_security_id(str(security_id))
            symbol = ref.symbol if ref else str(security_id)
            exchange = SEGMENT_TO_EXCHANGE.get(ref.exchange_segment if ref else "", "")

            return {
                "symbol": symbol,
                "exchange": exchange,
                "ltp": Decimal(str(round(ltp, 2))),
                "volume": 0,
                "timestamp": timestamp,
                "raw": {"feed_code": feed_code, "security_id": security_id},
            }

        elif feed_code == 4:  # Quote Data
            if len(message) < 50:
                return None
            unpacked = struct.unpack("<BHBIfHIfIIIffff", message[:50])
            security_id = unpacked[3]
            ltp = unpacked[4]
            timestamp = unpacked[6]
            volume = unpacked[8]

            ref = self._resolver.get_by_security_id(str(security_id))
            symbol = ref.symbol if ref else str(security_id)
            exchange = SEGMENT_TO_EXCHANGE.get(ref.exchange_segment if ref else "", "")

            return {
                "symbol": symbol,
                "exchange": exchange,
                "ltp": Decimal(str(round(ltp, 2))),
                "volume": volume,
                "timestamp": timestamp,
                "open": Decimal(str(round(unpacked[11], 2))),
                "close": Decimal(str(round(unpacked[12], 2))),
                "high": Decimal(str(round(unpacked[13], 2))),
                "low": Decimal(str(round(unpacked[14], 2))),
                "raw": {"feed_code": feed_code, "security_id": security_id},
            }

        elif feed_code == 8:  # Full Packet Data
            if len(message) < 162:
                return None
            unpacked = struct.unpack("<BHBIfHIfIIIIIIffff100s", message[:162])
            security_id = unpacked[3]
            ltp = unpacked[4]
            timestamp = unpacked[6]
            volume = unpacked[8]

            ref = self._resolver.get_by_security_id(str(security_id))
            symbol = ref.symbol if ref else str(security_id)
            exchange = SEGMENT_TO_EXCHANGE.get(ref.exchange_segment if ref else "", "")

            return {
                "symbol": symbol,
                "exchange": exchange,
                "ltp": Decimal(str(round(ltp, 2))),
                "volume": volume,
                "timestamp": timestamp,
                "open": Decimal(str(round(unpacked[14], 2))),
                "close": Decimal(str(round(unpacked[15], 2))),
                "high": Decimal(str(round(unpacked[16], 2))),
                "low": Decimal(str(round(unpacked[17], 2))),
                "raw": {"feed_code": feed_code, "security_id": security_id},
            }

        return None

    @staticmethod
    def _parse_tick(data: dict) -> dict | None:
        # Fallback for JSON-based ticks (e.g. if test mocks use JSON dicts)
        if not isinstance(data, dict):
            return None
        return {
            "symbol": data.get("symbol", data.get("tradingSymbol", "")),
            "exchange": data.get("exchange", ""),
            "ltp": Decimal(str(data.get("lastPrice", data.get("ltp", 0)))),
            "volume": int(data.get("volume", 0)),
            "timestamp": data.get("timestamp", ""),
            "raw": data,
        }

"""Upstox streaming adapter — real-time market data via WebSocket.

Uses sync threading (websocket-client library) for the WebSocket connection.
Runs the WebSocket in a background daemon thread.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal

from brokers.adapters.base_streaming import BaseWebSocketStreaming
from brokers.adapters.upstox.config import EXCHANGE_TO_SEGMENT

logger = logging.getLogger(__name__)

WS_URL = "wss://ws.upstox.com/feed/subscribe"


class UpstoxStreaming(BaseWebSocketStreaming):
    """Real-time market data streaming via Upstox WebSocket.

    Usage::

        streaming = UpstoxStreaming(access_token="...")
        streaming.on_tick = lambda tick: print(tick)
        streaming.subscribe("RELIANCE", "NSE")
        streaming.start()
        # ... later
        streaming.stop()
    """

    def __init__(
        self,
        access_token: str,
        ws_url: str = WS_URL,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 60.0,
    ):
        super().__init__(
            ws_url=ws_url,
            reconnect_delay=reconnect_delay,
            max_reconnect_delay=max_reconnect_delay,
            log_prefix="upstox_ws",
        )
        self._access_token = access_token

    def subscribe(self, symbol: str, exchange: str = "NSE") -> None:
        segment = EXCHANGE_TO_SEGMENT.get(exchange.upper(), exchange)
        key = f"{segment}|{symbol}"
        super().subscribe(key)

    def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None:
        segment = EXCHANGE_TO_SEGMENT.get(exchange.upper(), exchange)
        key = f"{segment}|{symbol}"
        super().unsubscribe(key)

    def _get_ws_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    def _build_subscribe_message(self, keys: list[str]) -> str:
        return json.dumps(
            {
                "guid": "subscribe",
                "method": "sub",
                "data": keys,
            }
        )

    def _build_unsubscribe_message(self, keys: list[str]) -> str:
        return json.dumps(
            {
                "guid": "unsubscribe",
                "method": "unsub",
                "data": keys,
            }
        )

    @staticmethod
    def _parse_tick(data: dict) -> dict | None:
        if not isinstance(data, dict):
            return None
        return {
            "symbol": data.get("symbol", data.get("trading_symbol", "")),
            "exchange": data.get("exchange", ""),
            "ltp": Decimal(str(data.get("last_price", data.get("ltp", 0)))),
            "volume": int(data.get("volume", 0)),
            "timestamp": data.get("timestamp", ""),
            "raw": data,
        }

"""Dhan Depth 20 adapter — L2 Market Data via WebSocket."""

from __future__ import annotations

import json
import logging
from typing import Callable, Any

from brokers.adapters.base_streaming import BaseWebSocketStreaming
from brokers.adapters.dhan.config import EXCHANGE_MAP
from brokers.adapters.dhan.identity import DhanInstrumentResolver

logger = logging.getLogger(__name__)

# 20-level market depth websocket URL
WS_URL = "wss://depth-api-feed.dhan.co/twentydepth"


class DhanDepth20Stream(BaseWebSocketStreaming):
    """Real-time Depth 20 (L2) market data via Dhan WebSocket."""

    def __init__(
        self,
        access_token: str | Callable[[], str],
        client_id: str,
        resolver: DhanInstrumentResolver | None = None,
        ws_url: str = WS_URL,
        reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 60.0,
    ):
        super().__init__(
            ws_url=ws_url,
            reconnect_delay=reconnect_delay,
            max_reconnect_delay=max_reconnect_delay,
            log_prefix="dhan_depth20",
        )
        self._access_token = access_token
        self._client_id = client_id
        self._resolver = resolver

        self.on_depth_update: Callable[[dict], Any] | None = None

    def subscribe(self, symbol: str, exchange: str = "NSE") -> None:
        try:
            ref = self._resolver.resolve(symbol, exchange)
            if ref:
                key = f"{ref.exchange_segment}|{ref.security_id}"
                super().subscribe(key)
                logger.info(f"Depth20 subscribed to {symbol} ({exchange}) as key {key}")
            else:
                segment = EXCHANGE_MAP.get(exchange.upper(), exchange)
                super().subscribe(f"{segment}|{symbol}")
        except Exception as e:
            logger.error(
                f"Depth20 failed to resolve/subscribe {symbol} on {exchange}: {e}"
            )
            segment = EXCHANGE_MAP.get(exchange.upper(), exchange)
            super().subscribe(f"{segment}|{symbol}")

    def unsubscribe(self, symbol: str, exchange: str = "NSE") -> None:
        try:
            ref = self._resolver.resolve(symbol, exchange)
            if ref:
                key = f"{ref.exchange_segment}|{ref.security_id}"
                super().unsubscribe(key)
                logger.info(
                    f"Depth20 unsubscribed from {symbol} ({exchange}) as key {key}"
                )
        except Exception as e:
            logger.error(
                f"Depth20 failed to resolve/unsubscribe {symbol} on {exchange}: {e}"
            )
            segment = EXCHANGE_MAP.get(exchange.upper(), exchange)
            super().unsubscribe(f"{segment}|{symbol}")

    def update_token(self, new_token: str) -> None:
        self._access_token = new_token

    def _get_access_token(self) -> str:
        if callable(self._access_token):
            return self._access_token()
        return self._access_token

    def _get_ws_url(self) -> str:
        token = self._get_access_token()
        return f"{self._ws_url}?token={token}&clientId={self._client_id}&authType=2"

    def _get_ws_headers(self) -> dict[str, str]:
        # Auth handled via query parameters, no headers required
        return {}

    def _build_subscribe_message(self, keys: list[str]) -> str:
        instrument_list = []
        for key in keys:
            parts = key.split("|")
            if len(parts) == 2:
                instrument_list.append(
                    {"ExchangeSegment": parts[0], "SecurityId": parts[1]}
                )

        return json.dumps(
            {
                "RequestCode": 23,
                "InstrumentCount": len(instrument_list),
                "InstrumentList": instrument_list,
            }
        )

    def _build_unsubscribe_message(self, keys: list[str]) -> str:
        # Standard un-subscribe request code is RequestCode + 1 (24)
        instrument_list = []
        for key in keys:
            parts = key.split("|")
            if len(parts) == 2:
                instrument_list.append(
                    {"ExchangeSegment": parts[0], "SecurityId": parts[1]}
                )
        return json.dumps(
            {
                "RequestCode": 24,
                "InstrumentCount": len(instrument_list),
                "InstrumentList": instrument_list,
            }
        )

    def _on_message(self, ws, message: str | bytes) -> None:
        try:
            # Struct parsing logic if binary (Little Endian format for Dhan)
            if isinstance(message, bytes):
                import struct

                # Check minimum length (e.g., 12 bytes header)
                if len(message) >= 12:
                    header = struct.unpack("<HBBII", message[:12])
                    response_code = header[1]
                    security_id = header[3]

                    levels = []
                    for i in range(20):
                        offset = 12 + (i * 16)
                        if offset + 16 > len(message):
                            break
                        price, qty, orders = struct.unpack_from("<dII", message, offset)
                        if qty > 0:
                            levels.append(
                                {
                                    "price": round(price, 2),
                                    "quantity": qty,
                                    "orders": orders,
                                }
                            )

                    data = {
                        "security_id": security_id,
                        "response_code": response_code,
                        "side": "bids" if response_code == 41 else "asks",
                        "levels": levels,
                        "is_binary": True,
                    }
                    if self.on_depth_update:
                        self.on_depth_update(data)
            else:
                data = json.loads(message)
                if self.on_depth_update:
                    self.on_depth_update(data)
        except Exception as e:
            logger.warning(f"Failed to parse depth20 stream message: {e}")

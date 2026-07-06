"""Dhan order stream adapter — real-time order updates via WebSocket."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from brokers_core.domain.constants.timeouts import DEFAULT_MAX_RECONNECT_DELAY, DEFAULT_RECONNECT_DELAY
from brokers_core.domain.entities import Order

from brokers_core.adapters.base_streaming import BaseWebSocketStreaming
from brokers_core.config.endpoints import Dhan

logger = logging.getLogger(__name__)

WS_ORDER_URL = Dhan.WS_ORDER


class DhanOrderStream(BaseWebSocketStreaming):
    """Real-time order execution updates via Dhan WebSocket.

    Subscribes to live order updates and fires callbacks for order
    status changes (e.g. FILLED, REJECTED).
    """

    def __init__(
        self,
        access_token: str | Callable[[], str],
        client_id: str,
        ws_url: str = WS_ORDER_URL,
        reconnect_delay: float = DEFAULT_RECONNECT_DELAY,
        max_reconnect_delay: float = DEFAULT_MAX_RECONNECT_DELAY,
    ):
        super().__init__(
            ws_url=ws_url,
            reconnect_delay=reconnect_delay,
            max_reconnect_delay=max_reconnect_delay,
            log_prefix="dhan_order_ws",
        )
        self._access_token = access_token
        self._client_id = client_id

        self.on_order_update: Callable[[Order], Any] | None = None

    def update_token(self, new_token: str) -> None:
        """Update the access token (for broadcast system compatibility)."""
        self._access_token = new_token

    def _get_access_token(self) -> str:
        """Get the current access token, calling the function if needed."""
        if callable(self._access_token):
            return self._access_token()
        return self._access_token

    def _get_ws_headers(self) -> dict[str, str]:
        # Connect headers might not be necessary if auth is in the first payload,
        # but kept for completeness
        return {}

    def _build_subscribe_message(self, keys: list[str]) -> str:
        # Dhan order updates require an auth message on connect
        return json.dumps(
            {
                "LoginReq": {
                    "MsgCode": 42,
                    "ClientId": self._client_id,
                    "Token": self._get_access_token(),
                },
                "UserType": "SELF",
            }
        )

    def _build_unsubscribe_message(self, keys: list[str]) -> str:
        return json.dumps({"type": "unsubscribe", "channel": "orders"})

    def _on_message(self, ws, message: str | bytes) -> None:
        """Process incoming WebSocket messages."""
        try:
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            data = json.loads(message)
            order = self._parse_order_update(data)
            if order and self.on_order_update:
                self.on_order_update(order)
            elif hasattr(self, "on_tick") and callable(self.on_tick):
                self.on_tick(data)
        except Exception as e:
            logger.warning(f"Failed to parse order stream message: {e}", exc_info=True)

    @staticmethod
    def _parse_order_update(data: dict) -> Order | None:
        """Parse raw Dhan order payload into domain Order entity."""
        if "orderId" not in data and "dhanOrderId" not in data:
            return None

        try:
            from brokers_core.adapters.dhan.mapper import map_order

            return map_order(data)
        except Exception as e:
            logger.error(f"Error mapping order update: {e}")
            return None

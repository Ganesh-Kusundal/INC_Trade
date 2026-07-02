"""Streaming capability group for Upstox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class StreamingCapability:
    """WebSocket feed authorization and market data streaming."""

    feed_authorizer: Any
    market_data_websocket: Any

    def subscribe(self, *args: Any, **kwargs: Any) -> Any:
        return self.market_data_websocket.subscribe(*args, **kwargs)

    def unsubscribe(self, *args: Any, **kwargs: Any) -> Any:
        return self.market_data_websocket.unsubscribe(*args, **kwargs)

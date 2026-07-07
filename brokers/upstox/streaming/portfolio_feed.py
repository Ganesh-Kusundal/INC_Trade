"""Upstox portfolio stream — subclasses :class:`BaseOrderStream`.

Connects to Upstox's portfolio stream (``wss://api.upstox.com/v3/feed/portfolio-stream``)
and delivers real-time order status changes, position updates, and trade fills.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, ClassVar

import websockets

from brokers.common.streaming.base_order_stream import BaseOrderStream
from brokers.infrastructure.logging import get_logger
from brokers.infrastructure.streaming.stream_health import (
    MarketTickEvent,
    OrderUpdateEvent,
)

logger = get_logger(__name__)

_UPSTOX_STATUS_MAPPING: dict[str, str] = {
    "put_order_req_received": "OPEN",
    "validation_pending": "OPEN",
    "open_pending": "OPEN",
    "open": "OPEN",
    "modify_pending": "OPEN",
    "modified": "OPEN",
    "cancelled": "CANCELLED",
    "cancel_pending": "OPEN",
    "rejected": "REJECTED",
    "complete": "FILLED",
    "expired": "EXPIRED",
    "trigger_pending": "OPEN",
}


# ── Decoder helpers (module-level for testability) ────────────────────────────


def _decode_portfolio_message(
    raw: str | bytes,
) -> list[MarketTickEvent | OrderUpdateEvent]:
    """Decode Upstox portfolio stream messages into domain events."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, dict):
        return []

    events: list[MarketTickEvent | OrderUpdateEvent] = []
    for update_type in ("orders", "positions", "holdings", "gtt_orders"):
        updates = data.get(update_type)
        if not isinstance(updates, list):
            continue
        for item in updates:
            if not isinstance(item, dict):
                continue
            if update_type == "orders":
                ev = _parse_order_update(item)
                if ev:
                    events.append(ev)
    return events


def _parse_order_update(data: dict[str, Any]) -> OrderUpdateEvent | None:
    try:
        order_id = str(data.get("order_id", ""))
        if not order_id:
            return None
        return OrderUpdateEvent(
            order_id=order_id,
            symbol=data.get("trading_symbol", data.get("instrument_token", "")),
            status=_normalize_status(data.get("status", data.get("order_status", ""))),
            side=data.get("transaction_type", data.get("side", "")),
            quantity=int(data.get("quantity", 0)),
            filled_quantity=int(data.get("filled_quantity", 0)),
            price=float(data.get("price", 0)),
            average_price=float(data.get("average_price", 0)),
            broker_id="upstox",
            raw=data,
            timestamp=datetime.now(timezone.utc),
        )
    except (ValueError, TypeError) as exc:
        logger.debug("upstox_order_parse_error", error=str(exc)[:100])
        return None


def _normalize_status(status: str) -> str:
    return _UPSTOX_STATUS_MAPPING.get(status.lower(), "UNKNOWN")


# ── Class ─────────────────────────────────────────────────────────────────────


class UpstoxPortfolioStream(BaseOrderStream):
    """Async portfolio stream for Upstox — subclass of :class:`BaseOrderStream`."""

    BROKER_ID: ClassVar[str] = "upstox"

    def __init__(
        self,
        *,
        http_client: Any,
        on_order: Callable[[OrderUpdateEvent], None] | None = None,
        on_health_change: Callable | None = None,
    ) -> None:
        super().__init__(on_order=on_order, on_health_change=on_health_change)
        self._http_client = http_client

    async def _resolve_url_and_headers(self) -> tuple[str, dict[str, str] | None]:
        # Lazy import to avoid circular — authorizer lives in same package
        from .authorizer import UpstoxFeedAuthorizer

        authorizer = UpstoxFeedAuthorizer(http_client=self._http_client)
        ws_url = await authorizer.authorize_portfolio_stream()
        return (ws_url, None)

    def _decode_message(self, raw: str | bytes) -> list[MarketTickEvent | OrderUpdateEvent]:
        return _decode_portfolio_message(raw)

    async def _connect_ws(self, url: str, extra_headers: dict[str, str] | None = None) -> Any:
        ws = await websockets.connect(
            url,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        )
        logger.info("upstox_portfolio_ws_connected")
        return ws

    async def _subscribe(self, transport: Any, plan: Any) -> None:
        await self._no_op_subscribe(transport, plan)


__all__ = ["UpstoxPortfolioStream"]

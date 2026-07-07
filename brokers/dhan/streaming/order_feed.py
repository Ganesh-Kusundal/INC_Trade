"""Dhan order update WebSocket feed — subclasses :class:`BaseOrderStream`.

Connect to Dhan's order stream (``wss://api.dhan.co/orders/v3/``) and
stream real-time order status changes and trade fill notifications.

Decoder helpers + status mapping are kept as module-level functions so
they can be tested in isolation (no orchestrator / WS mocking needed).
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

_DHAN_ORDER_WS_URL = "wss://api.dhan.co/orders/v3/"


# ── Status normalization (shared module) ───────────────────────────────────

from brokers.dhan.status_mapping import (
    DHAN_STATUS_TO_STRING as _DHAN_STATUS_MAPPING,
    normalize_status as _normalize_status,
)


# ── Decoder helpers (module-level for testability) ────────────────────────────


def _decode_order_message(raw: str | bytes) -> list[MarketTickEvent | OrderUpdateEvent]:
    """Decode Dhan order stream messages into ``OrderUpdateEvent``s."""
    result: list[MarketTickEvent | OrderUpdateEvent] = []
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return result

    if isinstance(data, dict):
        if data.get("Type") == "order_alert":
            ev = _parse_order(data)
            if ev:
                result.append(ev)
            return result
        if "data" in data and isinstance(data["data"], list):
            return _parse_order_list(data["data"])

    if isinstance(data, list):
        return _parse_order_list(data)

    return result


def _parse_order_list(items: list) -> list[MarketTickEvent | OrderUpdateEvent]:
    events: list[MarketTickEvent | OrderUpdateEvent] = []
    for item in items:
        if isinstance(item, dict) and item.get("Type") == "order_alert":
            ev = _parse_order(item)
            if ev:
                events.append(ev)
    return events


def _parse_order(data: dict[str, Any]) -> OrderUpdateEvent | None:
    try:
        order_id = str(data.get("orderNo", data.get("orderId", "")))
        if not order_id:
            return None
        return OrderUpdateEvent(
            order_id=order_id,
            symbol=data.get("tradingSymbol", data.get("trading_symbol", "")),
            status=_normalize_status(data.get("orderStatus", "")),
            side=data.get("transactionType", data.get("side", "")),
            quantity=int(data.get("tradedQty", data.get("quantity", 0))),
            filled_quantity=int(data.get("filledQty", data.get("filled_qty", 0))),
            price=float(data.get("price", 0)),
            average_price=float(data.get("avgTradePrice", data.get("average_price", 0))),
            broker_id="dhan",
            raw=data,
            timestamp=datetime.now(timezone.utc),
        )
    except (ValueError, TypeError) as exc:
        logger.debug("dhan_order_parse_error", error=str(exc)[:100])
        return None


# ── Class ─────────────────────────────────────────────────────────────────────


class DhanOrderFeed(BaseOrderStream):
    """Async order update feed for Dhan — subclass of :class:`BaseOrderStream`."""

    BROKER_ID: ClassVar[str] = "dhan"

    def __init__(
        self,
        *,
        client_id: str,
        access_token: str,
        on_order: Callable[[OrderUpdateEvent], None] | None = None,
        on_health_change: Callable | None = None,
    ) -> None:
        super().__init__(on_order=self._dispatch_order, on_health_change=on_health_change)
        self._client_id = client_id
        self._access_token = access_token
        # List of order callbacks so concurrent subscribers don't clobber.
        self._order_callbacks: list[Callable[[OrderUpdateEvent], None]] = []
        if on_order is not None:
            self._order_callbacks.append(on_order)
        # Ref-count concurrent order subscribers so the shared order feed is
        # only stopped when the last consumer unsubscribes.
        self._subscriber_count = 0

    async def _resolve_url_and_headers(self) -> tuple[str, dict[str, str] | None]:
        return (
            _DHAN_ORDER_WS_URL,
            {"client-id": self._client_id, "access-token": self._access_token},
        )

    def _decode_message(self, raw: str | bytes) -> list[MarketTickEvent | OrderUpdateEvent]:
        return _decode_order_message(raw)

    async def _connect_ws(self, url: str, extra_headers: dict[str, str] | None = None) -> Any:
        ws = await websockets.connect(
            url,
            additional_headers=extra_headers or {},
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        )
        logger.info("dhan_order_ws_connected")
        return ws

    async def _subscribe(self, transport: Any, plan: Any) -> None:
        await self._no_op_subscribe(transport, plan)

    def _dispatch_order(self, event: OrderUpdateEvent) -> None:
        """Fan an order update out to all registered order callbacks."""
        for cb in self._order_callbacks:
            try:
                cb(event)
            except Exception as exc:  # noqa: BLE001
                logger.warning("dhan_order_callback_error", error=str(exc)[:200])

    def set_order_callback(self, callback: Callable[[OrderUpdateEvent], None] | None) -> None:
        """Register an order callback. Appends rather than overwriting so
        multiple concurrent subscribers each receive order updates.
        """
        if callback is not None and callback not in self._order_callbacks:
            self._order_callbacks.append(callback)
        if self._orchestrator is not None:
            self._orchestrator.set_callbacks(on_order=self._dispatch_order)

    def add_subscriber(self) -> None:
        """Register a concurrent order subscriber (ref-counted)."""
        self._subscriber_count += 1

    async def remove_subscriber(self) -> None:
        """Unregister an order subscriber. Only stops the shared feed when
        the last consumer leaves (so a single unsubscribe never kills it
        for everyone else).
        """
        self._subscriber_count = max(0, self._subscriber_count - 1)
        if self._subscriber_count == 0:
            await self.stop()

    def update_token(self, access_token: str) -> None:
        """Hot-swap the access token (used after refresh)."""
        self._access_token = access_token


__all__ = ["DhanOrderFeed"]

"""DhanOrderStream — real-time order/trade updates via Dhan SDK WebSocket.

Extracted from the former monolithic ``brokers/dhan/websocket.py`` (Task 5.1).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from cachetools import TTLCache

from brokers.dhan.reconnecting_service import ReconnectingServiceMixin
from brokers.dhan.websocket._helpers import (
    _DhanContext,
    _sdk_order_update_class,
)
from domain import (
    Order,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Trade,
    Validity,
)
from infrastructure.event_bus import DomainEvent, EventBus
from infrastructure.lifecycle.lifecycle import (
    HealthState,
    HealthStatus,
    ManagedService,
)

logger = logging.getLogger(__name__)


class DhanOrderStream(ReconnectingServiceMixin, ManagedService):
    """Wraps the SDK's OrderUpdate for real-time order status updates.

    Implements :class:`ManagedService` (Phase B / B5) so the broker's
    :class:`LifecycleManager` can start, stop, and health-check the
    background thread. ``stop(timeout_seconds)`` joins the thread
    within the timeout; the previous ``disconnect()`` only set
    ``_stop_event`` and never joined, leaking the daemon thread on
    process exit.

    Reconnect/message-tracking state is owned by
    :class:`ReconnectingServiceMixin` — the same single source of truth
    used by ``DhanMarketFeed`` and ``BinaryDepthFeed``. The previous
    implementation duplicated ``_stop_event`` / ``_is_connected`` /
    ``_reconnect_count`` / ``_last_message_at`` and never bumped a
    message counter, so ``health()`` reported stale freshness values.
    """

    name = "dhan.order_stream"

    def __init__(
        self,
        client_id: str,
        access_token: str | None = None,
        access_token_fn: Callable[[], str] | None = None,
        event_bus: EventBus | None = None,
    ):
        self._context = _DhanContext(
            client_id,
            access_token=access_token,
            access_token_fn=access_token_fn,
        )
        self._order_update: Any | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._order_callbacks: list[Callable[[dict], None]] = []
        self._event_bus = event_bus
        # Cumulative filledQty per order — OMS expects incremental TRADE qty.
        self._last_cumulative_filled: TTLCache = TTLCache(maxsize=10000, ttl=3600)  # 1-hour TTL, bounds memory
        # Initialise the shared reconnect / message-tracking state
        # owned by the mixin (single source of truth across all
        # Dhan WS services).
        self._init_reconnect_state()

    def update_token(self, access_token: str) -> None:
        """Push a fresh token to the context (called by scheduler)."""
        if not access_token or access_token == self._context.get_access_token():
            return
        self._context.update_token(access_token)
        with self._lock:
            if self._order_update:
                self._order_update.access_token = access_token

    def connect(self) -> None:
        """Deprecated alias for :meth:`start`."""
        self.start()

    def start(self) -> None:
        """ManagedService protocol: start the order-stream thread.

        Idempotent — re-calling while the thread is alive is a no-op.
        """
        with self._lock:
            if self._thread and self._thread.is_alive():
                logger.warning("Order stream already connected")
                return
            self._stop_event.clear()
            self._is_connected = False
            self._order_update = _sdk_order_update_class()(dhan_context=self._context)
            self._order_update.on_update = self._on_order_update
            self._thread = threading.Thread(
                target=self._run,
                name=self.name,
                daemon=True,
            )
            self._thread.start()

    def _run(self) -> None:
        """Run the order-stream event loop with reconnection backoff.

        Uses :meth:`ReconnectingServiceMixin._backoff_sleep` so a
        ``stop()`` interrupts the backoff immediately. The
        :meth:`_on_clean_disconnect` / :meth:`_on_reconnect_failure`
        helpers own the ``_reconnect_count`` increment and backoff
        reset so the behaviour is uniform across all Dhan WS services.
        """
        import os

        backoff = self.INITIAL_BACKOFF
        max_reconnect_attempts = int(os.getenv("DHAN_MAX_RECONNECT_ATTEMPTS", "50"))
        cooldown_seconds = float(os.getenv("DHAN_RECONNECT_COOLDOWN_SECONDS", "300"))

        while not self._stop_event.is_set():
            with self._lock:
                if self._reconnect_count >= max_reconnect_attempts:
                    logger.critical(
                        "order_stream_max_reconnect_attempts_exceeded",
                        extra={
                            "attempts": self._reconnect_count,
                            "max_attempts": max_reconnect_attempts,
                        },
                    )
                    self._emit_reconnect_metric()
                    self._reconnect_count = 0
                    if self._stop_event.wait(timeout=cooldown_seconds):
                        return
                    logger.info("order_stream_reconnect_cooldown_complete")

            try:
                with self._lock:
                    ou = self._order_update
                if ou is None:
                    return
                ou.connect_to_dhan_websocket_sync()
                with self._lock:
                    self._is_connected = True
                backoff = self._on_clean_disconnect()
            except Exception as exc:
                logger.error("Order stream error: %s", exc)
                with self._lock:
                    self._is_connected = False
                backoff = self._on_reconnect_failure(backoff)
            if self._stop_event.is_set():
                break
            backoff = self._backoff_sleep(backoff)

    def disconnect(self, timeout_seconds: float = 5.0) -> None:
        """Deprecated alias for :meth:`stop`."""
        self.stop(timeout_seconds=timeout_seconds)

    def stop(self, timeout_seconds: float = 5.0) -> None:
        """ManagedService protocol: stop the order-stream thread.

        Sets ``_stop_event``, joins the thread within
        ``timeout_seconds``. The previous ``disconnect()`` did NOT
        join — the daemon thread was leaked on process exit. This
        implementation joins, matching the ManagedService contract.
        Idempotent.
        """
        self._stop_event.set()
        with self._lock:
            self._is_connected = False
            thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout_seconds)
            if thread.is_alive():
                logger.warning("dhan.order_stream thread did not stop within %ss", timeout_seconds)
        logger.info("Order stream stopped")

    def health(self) -> HealthStatus:
        """ManagedService protocol: return a point-in-time health snapshot."""
        with self._lock:
            thread_alive = bool(self._thread and self._thread.is_alive())
            is_connected = self._is_connected
            reconnect_count = self._reconnect_count
            message_count = self._message_count
            last_message_age = (
                (datetime.now(timezone.utc) - self._last_message_at).total_seconds()
                if self._last_message_at is not None
                else None
            )
        if thread_alive and is_connected:
            state = HealthState.HEALTHY
            detail = "running and connected"
        elif thread_alive and not is_connected:
            state = HealthState.DEGRADED
            detail = "thread running but stream not connected"
        else:
            state = HealthState.STOPPED
            detail = "not started"
        return HealthStatus(
            state=state,
            service=self.name,
            last_check=datetime.now(timezone.utc),
            detail=detail,
            metrics={
                "connected": is_connected,
                "thread_alive": thread_alive,
                "reconnect_count": reconnect_count,
                "message_count": message_count,
                "last_message_age_seconds": (
                    last_message_age if last_message_age is not None else -1
                ),
            },
        )

    def on_order_update(self, callback: Callable[[dict], None]) -> None:
        """Register a callback for order updates (mixin-managed lock)."""
        self._register_callback(self._order_callbacks, callback)

    def off_order_update(self, callback: Callable[[dict], None]) -> None:
        """Remove a previously registered order-update callback."""
        self._unregister_callback(self._order_callbacks, callback)

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._is_connected

    def _on_order_update(self, data: dict) -> None:
        if not data or data.get("Type") != "order_alert":
            return
        # Plan §7.2: stamp the freshness signal through the mixin so
        # health() reports the same value as every other Dhan WS
        # service. Previous implementation set _last_message_at
        # manually and never incremented a message counter — the
        # freshness signal was correct but the count was permanently
        # stuck at zero and a future health check would never see
        # message traffic.
        self._note_message_received()
        order_data = data.get("Data", {})
        transformed = self._transform_order(order_data)
        callbacks = self._snapshot_callbacks(self._order_callbacks)
        for cb in callbacks:
            try:
                cb(transformed)
            except Exception as exc:
                logger.error("Order callback error: %s", exc)
        self._publish_order_update(
            transformed,
            correlation_id=self.next_correlation_id(prefix="dhan.order_stream"),
        )

    @staticmethod
    def _transform_order(data: dict) -> dict:
        """Transform SDK order data to canonical format."""
        return {
            "order_id": str(data.get("orderNo", "")),
            "status": data.get("status", "UNKNOWN"),
            "symbol": data.get("tradingSymbol", ""),
            "exchange": data.get("exchangeSegment", "NSE"),
            "side": data.get("transactionType", "BUY"),
            "quantity": int(data.get("quantity", 0)),
            "filled_quantity": int(data.get("filledQty", 0)),
            "price": Decimal(str(data.get("price", "0"))),
            "average_price": Decimal(str(data.get("averagePrice", "0"))),
            "product_type": data.get("productType", "INTRADAY"),
            "order_type": data.get("orderType", "MARKET"),
            "validity": data.get("validity", "DAY"),
        }

    def _publish_order_update(self, data: dict, correlation_id: str | None = None) -> None:
        if self._event_bus is None:
            return
        try:
            status = OrderStatus.normalize(str(data.get("status", "OPEN")))
            side = Side.BUY if str(data.get("side", "")).upper() == "BUY" else Side.SELL
            order_type = OrderType(str(data.get("order_type", "MARKET")).upper())
            product_type = ProductType(str(data.get("product_type", "INTRADAY")).upper())
            validity = Validity(str(data.get("validity", "DAY")).upper())
            order = Order(
                order_id=str(data.get("order_id", "")),
                symbol=str(data.get("symbol", "")),
                exchange=str(data.get("exchange", "NSE")),
                side=side,
                order_type=order_type,
                quantity=int(data.get("quantity", 0)),
                filled_quantity=int(data.get("filled_quantity", 0)),
                price=data.get("price", Decimal("0")),
                avg_price=data.get("average_price", Decimal("0")),
                product_type=product_type,
                validity=validity,
                status=status,
                timestamp=datetime.now(timezone.utc),
            )
            self._event_bus.publish(
                DomainEvent.now(
                    "ORDER_UPDATED",
                    {"order": order},
                    symbol=order.symbol,
                    source="DhanOrderStream",
                    correlation_id=correlation_id,
                )
            )
            # If the update indicates a fill, also publish a TRADE event so the
            # PositionManager can update. Dhan sends cumulative filledQty; OMS
            # expects incremental trade quantity per event.
            cumulative_filled = int(data.get("filled_quantity", 0))
            avg = data.get("average_price", Decimal("0"))
            order_id = order.order_id
            previous_filled = self._last_cumulative_filled.get(order_id, 0)
            incremental = cumulative_filled - previous_filled
            if cumulative_filled > previous_filled:
                self._last_cumulative_filled[order_id] = cumulative_filled
            if incremental > 0 and avg > 0:
                trade = Trade(
                    trade_id=f"{order.order_id}:{cumulative_filled}",
                    order_id=order.order_id,
                    symbol=order.symbol,
                    exchange=order.exchange,
                    side=side,
                    quantity=incremental,
                    price=avg,
                    timestamp=datetime.now(timezone.utc),
                    product_type=product_type,
                )
                self._event_bus.publish(
                    DomainEvent.now(
                        "TRADE",
                        {"trade": trade},
                        symbol=trade.symbol,
                        source="DhanOrderStream",
                        correlation_id=correlation_id,
                    )
                )
        except Exception as exc:
            logger.error("EventBus ORDER_UPDATED publish error: %s", exc)

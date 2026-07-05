"""OrderManagementSystem — orchestrates order placement with validation and routing.

Architecture::

    AccountHandle.place_order()
        │
        ▼
    OrderManagementSystem
        │
        ├── 1. Validate fields (domain validators)
        ├── 2. Check kill switch
        ├── 3. Run pre-trade risk check (if RiskManagerPort wired)
        ├── 4. Check idempotency (correlation_id cache)
        ├── 5. Route to broker via ExecutionRouter
        ├── 6. Save to OrderRepository
        └── 7. Return OrderResponse

The OMS lives in the trading bounded context. It receives ports directly
(not via services/) to maintain clean layer boundaries. All validation uses
``domain.validators.order_validator`` — no delegation to ``services/order_service.py``.

Thread Safety:
    Thread-safe via RLock for concurrent access from streaming callbacks
    and API calls. The idempotency cache and order repository both use
    their own locks.
"""

from __future__ import annotations

import logging
import threading
import time
from decimal import Decimal
from typing import Any

from inc_trade.domain.entities import (
    FillResult,
    Order,
    OrderResponse,
    RiskCheckRequest,
)
from inc_trade.domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from inc_trade.domain.events import (
    EVENT_ORDER_CANCELLED,
    EVENT_ORDER_MODIFIED,
    EVENT_ORDER_PLACED,
    EVENT_ORDER_REJECTED,
    OrderCancelledEvent,
    OrderModifiedEvent,
    OrderPlacedEvent,
    OrderRejectedEvent,
    OrderStateChangeEvent,
)
from inc_trade.domain.exceptions import BrokerError
from inc_trade.domain.validators.order_validator import (
    validate_exchange,
    validate_limit_price,
    validate_order,
    validate_price,
    validate_quantity,
    validate_symbol,
    validate_trigger_price,
)
from inc_trade.ports.event_publisher import EventPublisherPort
from inc_trade.ports.fill_detection import FillDetectionPort
from inc_trade.ports.risk_manager import RiskManagerPort
from inc_trade.trading.audit import OrderStateChange
from inc_trade.trading.execution_router import ExecutionRouter
from inc_trade.trading.order_repository import OrderRepository

logger = logging.getLogger(__name__)


class _IdempotencyEntry:
    """Internal idempotency cache entry with TTL."""

    __slots__ = ("response", "expires_at")

    def __init__(self, response: OrderResponse, ttl_seconds: float = 86400.0) -> None:
        self.response = response
        self.expires_at = time.monotonic() + ttl_seconds

    @property
    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at


class OrderManagementSystem:
    """Orchestrates order placement through validation, idempotency,
    kill switch, repository tracking, and execution routing.

    This is the central orchestrator for all trading operations. Every
    order flows through this system, ensuring consistent validation,
    idempotency, and state tracking.

    Args:
        execution_router: Routes orders to the correct broker adapter.
        order_repository: Local order state tracker.
        kill_switch: When True, blocks all order placement. Defaults to False.
        kill_switch_message: Custom message when kill switch is active.
        idempotency_ttl_seconds: TTL for idempotency cache entries
            (default: 24 hours).
        risk_manager: Optional pre-trade risk check port. When provided, the
            OMS invokes ``RiskManagerPort.check_order`` after validation and
            kill switch but before idempotency/routing. Hard rejections are
            returned as ``OrderResponse.fail(error_code="RISK_CHECK_REJECTED")``;
            exceptions are logged and treated as fail-open.
    """

    def __init__(
        self,
        execution_router: ExecutionRouter,
        order_repository: OrderRepository,
        kill_switch: bool = False,
        kill_switch_message: str = "Order placement is currently disabled (kill switch active)",
        idempotency_ttl_seconds: float = 86400.0,
        event_bus: EventPublisherPort | None = None,
        fill_detector: FillDetectionPort | None = None,
        risk_manager: RiskManagerPort | None = None,
    ) -> None:
        self._router = execution_router
        self._repository = order_repository
        self._kill_switch = kill_switch
        self._kill_switch_message = kill_switch_message
        self._idempotency_ttl = idempotency_ttl_seconds
        self._event_bus = event_bus
        self._fill_detector = fill_detector
        self._risk_manager = risk_manager
        self._lock = threading.RLock()
        # correlation_id → _IdempotencyEntry
        self._idempotency_cache: dict[str, _IdempotencyEntry] = {}
        # Lightweight metrics
        self._metrics: dict[str, int] = {
            "orders_placed": 0,
            "orders_rejected": 0,
            "orders_kill_switched": 0,
            "idempotency_hits": 0,
            "cancellations": 0,
            "modifications": 0,
            "fills_received": 0,
            "validation_failures": 0,
            "broker_errors": 0,
            "risk_check_rejections": 0,
        }

        # Register fill detection callback if provided
        if fill_detector is not None:
            fill_detector.on_fill(self._on_fill_detected)
            logger.info("OMS fill detection enabled via %s", fill_detector.__class__.__name__)

        if risk_manager is not None:
            logger.info("OMS risk check enabled via %s", risk_manager.__class__.__name__)

    def metrics(self) -> dict[str, int]:
        """Return a snapshot of OMS metrics.

        Keys:
            - orders_placed — successful placements
            - orders_rejected — broker-rejected
            - orders_kill_switched — blocked by kill switch
            - idempotency_hits — duplicates via correlation_id
            - cancellations, modifications
            - fills_received
            - validation_failures
            - broker_errors
            - risk_check_rejections — blocked by pre-trade risk check
        """
        return dict(self._metrics)

    # ── Kill Switch ────────────────────────────────────────────────────

    @property
    def kill_switch(self) -> bool:
        """Whether order placement is currently blocked."""
        return self._kill_switch

    @kill_switch.setter
    def kill_switch(self, value: bool) -> None:
        """Enable or disable the kill switch.

        Args:
            value: True to block orders, False to allow.
        """
        self._kill_switch = value
        logger.info("OMS kill switch %s", "enabled" if value else "disabled")

    # ── Idempotency Cache ──────────────────────────────────────────────

    def clear_idempotency_cache(self) -> None:
        """Clear all idempotency cache entries."""
        with self._lock:
            self._idempotency_cache.clear()

    def _check_idempotency(self, correlation_id: str) -> OrderResponse | None:
        """Check if a correlation_id has been used before.

        Args:
            correlation_id: Unique order identifier.

        Returns:
            Cached OrderResponse if found and not expired, None otherwise.
        """
        if not correlation_id:
            return None
        with self._lock:
            entry = self._idempotency_cache.get(correlation_id)
            if entry is None:
                return None
            if entry.is_expired:
                del self._idempotency_cache[correlation_id]
                return None
            logger.debug(
                "OMS idempotency HIT for correlation_id=%s",
                correlation_id,
            )
            return entry.response

    def _cache_idempotency(self, correlation_id: str, response: OrderResponse) -> None:
        """Cache an OrderResponse for idempotency checking.

        Args:
            correlation_id: Unique order identifier.
            response: OrderResponse to cache.
        """
        if not correlation_id:
            return
        with self._lock:
            self._idempotency_cache[correlation_id] = _IdempotencyEntry(
                response=response,
                ttl_seconds=self._idempotency_ttl,
            )

    # ── Fill Detection ──────────────────────────────────────────────────

    def _on_fill_detected(self, fill: FillResult) -> None:
        """Handle a fill detected by the broker's fill detection adapter.

        Updates the order repository and publishes an OrderFilledEvent.
        Called from the fill detection adapter's thread.

        Args:
            fill: FillResult describing the executed trade.
        """
        # Look up order to find account_id
        logger.info(
            "Fill detected: order=%s %s qty=%d @ %s (complete=%s)",
            fill.order_id,
            fill.symbol,
            fill.fill_quantity,
            fill.is_complete,
        )

        self._metrics["fills_received"] += 1

        # Update order in repository (inside lock for thread safety)
        with self._lock:
            order = self._repository.get(fill.order_id)
            if order is None:
                logger.warning(
                    "Fill for unknown order: %s — cannot update status",
                    fill.order_id,
                )
                return

            previous_status = order.status
            new_filled_qty = order.filled_quantity + fill.fill_quantity
            new_status = OrderStatus.FILLED if fill.is_complete else OrderStatus.PARTIALLY_FILLED
            self._repository.update_status(
                order_id=fill.order_id,
                new_status=new_status,
                filled_quantity=new_filled_qty,
                message=f"Fill: {fill.fill_quantity} @ {fill.fill_price}",
            )

        # Record audit transition and publish event outside the lock
        self._record_transition(
            order_id=fill.order_id,
            from_status=previous_status,
            to_status=new_status,
            reason="fill",
            correlation_id=order.correlation_id,
            metadata={
                "fill_price": str(fill.fill_price),
                "fill_quantity": str(fill.fill_quantity),
            },
        )
        self._publish_event(
            OrderFilledEvent(
                account_id=self._repository.get_account_for_order(fill.order_id),
                order_id=fill.order_id,
                symbol=fill.symbol,
                fill_price=fill.fill_price,
                fill_quantity=fill.fill_quantity,
                remaining_quantity=fill.remaining_quantity,
                is_complete=fill.is_complete,
                timestamp=fill.fill_timestamp,
            )
        )

    # ── Audit Trail ────────────────────────────────────────────────────

    def _record_transition(
        self,
        order_id: str,
        from_status: OrderStatus,
        to_status: OrderStatus,
        reason: str,
        correlation_id: str = "",
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Persist a single order state transition and publish its event.

        This is the single funnel through which every audit-trail transition
        flows. Callers must not write to the repository's history directly.

        Args:
            order_id: Order whose state changed.
            from_status: Status the order transitioned from.
            to_status: Status the order transitioned to.
            reason: Free-form reason code (e.g. "place", "cancel", "fill").
            correlation_id: Idempotency key carried on the change record.
            metadata: Optional transition-specific key/value context.
        """
        change = OrderStateChange(
            order_id=order_id,
            correlation_id=correlation_id,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            metadata=metadata or {},
        )
        self._repository.record_state_change(change)
        self._publish_event(
            OrderStateChangeEvent(
                order_id=order_id,
                correlation_id=correlation_id,
                from_status=from_status.value
                if hasattr(from_status, "value")
                else str(from_status),
                to_status=to_status.value if hasattr(to_status, "value") else str(to_status),
                reason=reason,
            )
        )

    # ── Core Order Operations ──────────────────────────────────────────

    def place_order(
        self,
        account_id: str,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = Decimal("0"),
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str = "",
    ) -> OrderResponse:
        """Place an order with full lifecycle management.

        1. Validate fields (symbol, exchange, quantity, price, trigger_price)
        2. Check kill switch
        3. Run pre-trade risk check (if RiskManagerPort is wired)
        4. Check idempotency (correlation_id)
        5. Route to correct broker via ExecutionRouter
        6. Save to OrderRepository
        7. Return OrderResponse

        Args:
            account_id: Account identifier for routing.
            symbol: Instrument symbol.
            exchange: Exchange code.
            side: BUY or SELL.
            quantity: Number of shares/contracts.
            order_type: MARKET, LIMIT, etc.
            price: Limit price (for LIMIT orders).
            product_type: INTRADAY, DELIVERY, etc.
            validity: DAY, IOC, etc.
            trigger_price: Stop-loss trigger price.
            correlation_id: Unique ID for idempotency (optional).

        Returns:
            OrderResponse with success status and order details.

        Raises:
            ValidationError: If any validation rule is violated.
            BrokerError: If kill switch is active or routing fails.
        """
        # Step 1: Validate fields
        try:
            validate_order(
                symbol=symbol,
                exchange=exchange,
                quantity=quantity,
                order_type=order_type,
                price=price,
                trigger_price=trigger_price,
            )
        except Exception:
            self._metrics["validation_failures"] += 1
            raise

        # Step 2: Check kill switch
        if self._kill_switch:
            self._metrics["orders_kill_switched"] += 1
            logger.warning(
                "OMS kill switch BLOCKED order: %s %d %s @ %s",
                side.value,
                quantity,
                symbol,
                price,
            )
            return OrderResponse.fail(
                message=self._kill_switch_message,
                error_code="KILL_SWITCH_ACTIVE",
            )

        # Step 3: Pre-trade risk check (skipped when no risk manager is wired).
        # Fail-open on exceptions: a buggy risk manager must not break trading,
        # but a hard rejection from a healthy manager short-circuits the order
        # with a RISK_CHECK_REJECTED error code. The check is intentionally
        # outside the RLock (the risk manager is responsible for its own
        # concurrency guarantees) to keep the OMS critical section short.
        if self._risk_manager is not None:
            try:
                risk_request = RiskCheckRequest(
                    symbol=symbol,
                    exchange=exchange,
                    side=side,
                    quantity=quantity,
                    price=price,
                    order_type=order_type,
                )
                risk_result = self._risk_manager.check_order(risk_request)
            except Exception as exc:
                logger.warning(
                    "oms_risk_check_failed",
                    extra={
                        "symbol": symbol,
                        "exchange": exchange,
                        "error": str(exc),
                    },
                )
            else:
                if not risk_result.allowed:
                    self._metrics["risk_check_rejections"] += 1
                    reason = risk_result.reason or "rejected by risk manager"
                    logger.warning(
                        "OMS risk check REJECTED order: %s %d %s @ %s (%s)",
                        side.value,
                        quantity,
                        symbol,
                        price,
                        reason,
                    )
                    return OrderResponse.fail(
                        message=f"Risk check failed: {reason}",
                        error_code="RISK_CHECK_REJECTED",
                    )

        # Step 4: Check idempotency
        if correlation_id:
            cached = self._check_idempotency(correlation_id)
            if cached is not None:
                self._metrics["idempotency_hits"] += 1
                return OrderResponse.already_executed(cached.order_id)

        # Step 5: Route to correct broker
        try:
            response = self._router.place_order(
                account_id=account_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                order_type=order_type,
                price=price,
                product_type=product_type,
                validity=validity,
                trigger_price=trigger_price,
            )
        except Exception:
            self._metrics["broker_errors"] += 1
            raise

        # Step 6: Save to repository (if we got an order_id)
        if response.order_id:
            order = Order(
                order_id=response.order_id,
                symbol=symbol,
                exchange=exchange,
                side=side,
                quantity=quantity,
                status=response.status,
                price=price,
                trigger_price=trigger_price,
                order_type=order_type,
                product_type=product_type,
                validity=validity,
                message=response.message,
                correlation_id=correlation_id,
            )
            self._repository.save(order, account_id=account_id)
            if response.success:
                self._metrics["orders_placed"] += 1
            else:
                self._metrics["orders_rejected"] += 1

            # Record audit-trail transition: PENDING -> response.status
            self._record_transition(
                order_id=response.order_id,
                from_status=OrderStatus.PENDING,
                to_status=response.status,
                reason="reject" if not response.success else "place",
                correlation_id=correlation_id,
            )

        # Step 7: Cache idempotency
        if correlation_id and response.order_id:
            self._cache_idempotency(correlation_id, response)

        # Step 8: Publish order placed event
        self._publish_order_placed(
            account_id,
            response,
            symbol,
            exchange,
            side,
            quantity,
            order_type,
            price,
            correlation_id,
        )

        return response

    # ── Event Publishing ────────────────────────────────────────────────

    def _publish_event(self, event: Any) -> None:
        """Publish an event to the event bus (if wired)."""
        if self._event_bus is not None:
            self._event_bus.publish(event)

    def _publish_order_placed(
        self,
        account_id: str,
        response: OrderResponse,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: OrderType,
        price: Decimal,
        correlation_id: str,
    ) -> None:
        """Publish OrderPlacedEvent after successful placement."""
        if not response.success:
            self._publish_event(
                OrderRejectedEvent(
                    account_id=account_id,
                    order_id=response.order_id or "",
                    symbol=symbol,
                    reason=response.message or "",
                    correlation_id=correlation_id,
                )
            )
            return
        self._publish_event(
            OrderPlacedEvent(
                account_id=account_id,
                order_id=response.order_id or "",
                symbol=symbol,
                exchange=exchange,
                side=side.value if hasattr(side, "value") else str(side),
                quantity=quantity,
                order_type=order_type.value if hasattr(order_type, "value") else str(order_type),
                price=price,
                correlation_id=correlation_id,
            )
        )

    def _publish_order_cancelled(
        self, account_id: str, order_id: str, response: OrderResponse
    ) -> None:
        """Publish OrderCancelledEvent after cancellation."""
        if not response.success:
            return
        self._publish_event(
            OrderCancelledEvent(
                account_id=account_id,
                order_id=order_id,
                symbol="",
                cancelled_quantity=0,
            )
        )

    def _publish_order_modified(
        self, account_id: str, order_id: str, response: OrderResponse
    ) -> None:
        """Publish OrderModifiedEvent after modification."""
        if not response.success:
            return
        self._publish_event(
            OrderModifiedEvent(
                account_id=account_id,
                order_id=order_id,
                symbol="",
            )
        )

    def cancel_order(self, account_id: str, order_id: str) -> OrderResponse:
        """Cancel an order.

        Args:
            account_id: Account identifier for routing.
            order_id: Order identifier to cancel.

        Returns:
            OrderResponse with cancellation status.
        """
        if not order_id:
            return OrderResponse.fail("Order ID is required", error_code="VALIDATION_FAILED")

        response = self._router.cancel_order(account_id=account_id, order_id=order_id)
        if response.success:
            self._metrics["cancellations"] += 1

        # Update repository status
        if response.success:
            previous = self._repository.get(order_id)
            previous_status = previous.status if previous is not None else OrderStatus.OPEN
            self._repository.update_status(
                order_id=order_id,
                new_status=OrderStatus.CANCELLED,
                message=response.message,
            )
            self._record_transition(
                order_id=order_id,
                from_status=previous_status,
                to_status=OrderStatus.CANCELLED,
                reason="cancel",
                correlation_id=previous.correlation_id if previous is not None else "",
            )

        self._publish_order_cancelled(account_id, order_id, response)

        return response

    def modify_order(
        self,
        account_id: str,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        validity: Validity | None = None,
    ) -> OrderResponse:
        """Modify an existing order.

        Args:
            account_id: Account identifier for routing.
            order_id: Order identifier to modify.
            quantity: New quantity (optional).
            price: New price (optional).
            order_type: New order type (optional).
            validity: New validity (optional).

        Returns:
            OrderResponse with modification status.
        """
        if not order_id:
            return OrderResponse.fail("Order ID is required", error_code="VALIDATION_FAILED")

        response = self._router.modify_order(
            account_id=account_id,
            order_id=order_id,
            quantity=quantity,
            price=price,
            order_type=order_type,
            validity=validity,
        )
        if response.success:
            self._metrics["modifications"] += 1
            current = self._repository.get(order_id)
            current_status = current.status if current is not None else OrderStatus.OPEN
            self._record_transition(
                order_id=order_id,
                from_status=current_status,
                to_status=current_status,
                reason="modify",
                correlation_id=current.correlation_id if current is not None else "",
            )

        self._publish_order_modified(account_id, order_id, response)

        return response

    def get_order(self, account_id: str, order_id: str) -> Order | None:
        """Get order details.

        Checks local OrderRepository first, then falls back to broker.

        Args:
            account_id: Account identifier for routing.
            order_id: Order identifier.

        Returns:
            Order if found, None otherwise.
        """
        # Check local repository first (fast path)
        local = self._repository.get(order_id)
        if local is not None:
            return local
        # Fall back to broker
        return self._router.get_order(account_id=account_id, order_id=order_id)

    def get_orderbook(self, account_id: str) -> list[Order]:
        """Get all orders for an account.

        Args:
            account_id: Account identifier for routing.

        Returns:
            List of Order objects from the broker.
        """
        return self._router.get_orderbook(account_id=account_id)

    def get_active_orders(self, account_id: str = "") -> list[Order]:
        """Get all active (non-terminal) orders from local repository.

        Args:
            account_id: If provided, filters to this account only.

        Returns:
            List of active Order objects.
        """
        return self._repository.get_active(account_id=account_id)

    def __repr__(self) -> str:
        return (
            f"OrderManagementSystem("
            f"kill_switch={self._kill_switch}, "
            f"brokers={self._router.registered_brokers}, "
            f"orders={self._repository.count()})"
        )

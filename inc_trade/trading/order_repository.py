"""OrderRepository — thread-safe in-memory order store for the trading context.

Architecture:
    Lives in the trading bounded context. Provides local order tracking
    that complements the broker's remote order state. Thread-safe for
    concurrent access from streaming callbacks and API calls.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from inc_trade.domain.entities import Order
from inc_trade.domain.enums import OrderStatus
from inc_trade.trading.audit import OrderStateChange, OrderStateHistory


class OrderRepository:
    """Thread-safe in-memory order repository.

    Provides local order tracking with identity, status querying,
    and lifecycle management. Designed to complement (not replace)
    the broker's remote order state.

    Thread-safe via RLock for concurrent access from streaming
    callbacks and API calls.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._orders: dict[str, Order] = {}
        self._account_orders: dict[str, set[str]] = {}  # account_id -> set of order_ids
        self._order_accounts: dict[str, str] = {}  # order_id -> account_id
        self._state_history: dict[str, OrderStateHistory] = {}  # order_id -> audit trail

    # ── Write Operations ───────────────────────────────────────────────

    def save(self, order: Order, account_id: str = "") -> None:
        """Store an order.

        If account_id is provided, the order is also indexed by account
        for efficient querying.

        Args:
            order: Order domain entity to store.
            account_id: Optional account identifier for indexing.
        """
        with self._lock:
            self._orders[order.order_id] = order
            if account_id:
                self._account_orders.setdefault(account_id, set()).add(order.order_id)
                # Build reverse index: order_id -> account_id
                self._order_accounts[order.order_id] = account_id

    def get_account_for_order(self, order_id: str) -> str:
        """Get the account_id that owns an order.

        Args:
            order_id: Order identifier.

        Returns:
            Account identifier, or empty string if not found.
        """
        with self._lock:
            return self._order_accounts.get(order_id, "")

    def update_status(
        self,
        order_id: str,
        new_status: OrderStatus,
        filled_quantity: int | None = None,
        message: str = "",
    ) -> Order | None:
        """Update the status of an existing order.

        Returns the updated Order, or None if the order_id is unknown.

        Args:
            order_id: Order identifier.
            new_status: New OrderStatus.
            filled_quantity: Updated filled quantity (if changed).
            message: Optional status message.
        """
        with self._lock:
            existing = self._orders.get(order_id)
            if existing is None:
                return None

            updated = Order(
                order_id=existing.order_id,
                symbol=existing.symbol,
                exchange=existing.exchange,
                side=existing.side,
                quantity=existing.quantity,
                status=new_status,
                price=existing.price,
                trigger_price=existing.trigger_price,
                order_type=existing.order_type,
                product_type=existing.product_type,
                validity=existing.validity,
                filled_quantity=filled_quantity
                if filled_quantity is not None
                else existing.filled_quantity,
                message=message or existing.message,
                timestamp=datetime.now(UTC),
                correlation_id=existing.correlation_id,
            )
            self._orders[order_id] = updated
            return updated

    # ── Read Operations ────────────────────────────────────────────────

    def get(self, order_id: str) -> Order | None:
        """Look up an order by ID.

        Args:
            order_id: Order identifier.

        Returns:
            Order if found, None otherwise.
        """
        with self._lock:
            return self._orders.get(order_id)

    def get_by_account(self, account_id: str) -> list[Order]:
        """Get all orders for a specific account.

        Args:
            account_id: Account identifier.

        Returns:
            List of Order objects (empty list if none found).
        """
        with self._lock:
            order_ids = self._account_orders.get(account_id, set())
            return [self._orders[oid] for oid in order_ids if oid in self._orders]

    def get_active(self, account_id: str = "") -> list[Order]:
        """Get all active (non-terminal) orders.

        Args:
            account_id: If provided, filters to this account only.

        Returns:
            List of active Order objects.
        """
        with self._lock:
            orders = (
                [o for o in self._orders.values()]
                if not account_id
                else self.get_by_account(account_id)
            )
            return [o for o in orders if o.is_active()]

    def get_all(self) -> list[Order]:
        """Get all stored orders.

        Returns:
            List of all Order objects.
        """
        with self._lock:
            return list(self._orders.values())

    def count(self) -> int:
        """Total number of stored orders.

        Returns:
            Order count.
        """
        with self._lock:
            return len(self._orders)

    # ── Maintenance ────────────────────────────────────────────────────

    def clear(self) -> None:
        """Clear all orders (primarily for testing)."""
        with self._lock:
            self._orders.clear()
            self._account_orders.clear()
            self._order_accounts.clear()

    def __contains__(self, order_id: str) -> bool:
        with self._lock:
            return order_id in self._orders

    # ── Audit Trail ─────────────────────────────────────────────────────

    def record_state_change(self, change: OrderStateChange) -> None:
        """Append a state transition to an order's audit history.

        If the order has no history yet, a new ``OrderStateHistory`` is
        created. Subsequent calls accumulate transitions in order.

        Args:
            change: The transition to record. ``change.order_id`` selects
                which order's history is updated.
        """
        with self._lock:
            existing = self._state_history.get(
                change.order_id, OrderStateHistory(order_id=change.order_id)
            )
            self._state_history[change.order_id] = existing.append(change)

    def history_for(self, order_id: str) -> OrderStateHistory:
        """Return the audit history for an order.

        Returns an empty ``OrderStateHistory`` (not ``None``) for unknown
        order IDs so callers can iterate unconditionally.

        Args:
            order_id: Order identifier.

        Returns:
            The order's history, or an empty history if no transitions have
            been recorded.
        """
        with self._lock:
            return self._state_history.get(order_id, OrderStateHistory(order_id=order_id))

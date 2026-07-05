"""Execution Router — routes order execution to the correct broker adapter by account.

Architecture::

    TradingContext
        │
        ▼
    AccountHandle.place_order()
        │
        ├── OMS path (new): OrderManagementSystem
        │       │
        │       ├── 1. Validate fields (domain validators)
        │       ├── 2. Check kill switch
        │       ├── 3. Check idempotency (correlation_id)
        │       ├── 4. Route to broker via ExecutionRouter
        │       └── 5. Save to OrderRepository
        │
        └── Legacy path (fallback): direct OrderExecutionPort

    ExecutionRouter lives in the trading bounded context. It maps account
    identifiers to the appropriate OrderExecutionPort implementation.

    Account IDs follow the convention ``{broker_id}/{account_name}``
    (e.g., ``"dhan/default"``, ``"upstox/primary"``). The router extracts
    the broker_id prefix to find the correct adapter.

Thread Safety:
    ExecutionRouter is thread-safe via RLock for concurrent access from
    streaming callbacks and API calls.
"""

from __future__ import annotations

import logging
import threading
from decimal import Decimal
from typing import Any

from inc_trade.domain.entities import Order, OrderResponse
from inc_trade.domain.enums import OrderType, ProductType, Side, Validity
from inc_trade.domain.exceptions import BrokerError
from inc_trade.ports.order_execution import OrderExecutionPort

logger = logging.getLogger(__name__)


class ExecutionRouter:
    """Routes order execution to the correct broker adapter by account.

    Maintains a registry of ``OrderExecutionPort`` implementations indexed
    by broker_id. Account IDs follow the pattern ``{broker_id}/{account_name}``
    (e.g., ``"dhan/default"``). The router splits on ``/`` to extract the
    broker_id and find the correct adapter.

    Args:
        adapters: Optional initial mapping of broker_id → OrderExecutionPort.
    """

    def __init__(
        self,
        adapters: dict[str, OrderExecutionPort] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._adapters: dict[str, OrderExecutionPort] = dict(adapters or {})

    # ── Adapter Management ─────────────────────────────────────────────

    def register_adapter(
        self,
        broker_id: str,
        adapter: OrderExecutionPort,
    ) -> None:
        """Register an OrderExecutionPort for a broker.

        Args:
            broker_id: Canonical broker identifier (e.g., ``"dhan"``).
            adapter: OrderExecutionPort implementation.
        """
        with self._lock:
            self._adapters[broker_id] = adapter
            logger.info(
                "ExecutionRouter: registered adapter for broker",
                extra={"broker_id": broker_id},
            )

    def unregister_adapter(self, broker_id: str) -> bool:
        """Remove an adapter registration.

        Args:
            broker_id: Broker identifier.

        Returns:
            True if found and removed, False otherwise.
        """
        with self._lock:
            if broker_id in self._adapters:
                del self._adapters[broker_id]
                return True
            return False

    @property
    def registered_brokers(self) -> list[str]:
        """List of registered broker IDs."""
        with self._lock:
            return list(self._adapters.keys())

    # ── Routing ────────────────────────────────────────────────────────

    def _parse_account_id(self, account_id: str) -> str:
        """Extract broker_id from an account ID.

        Parses ``"dhan/default"`` → ``"dhan"``.

        Args:
            account_id: Account identifier (e.g., ``"dhan/default"``).

        Returns:
            Broker identifier string.

        Raises:
            BrokerError: If account_id format is invalid.
        """
        if "/" not in account_id:
            raise BrokerError(
                f"Invalid account_id format: {account_id!r}. "
                "Expected '{broker_id}/{account_name}' (e.g., 'dhan/default')"
            )
        return account_id.split("/")[0]

    def route(self, account_id: str) -> OrderExecutionPort:
        """Find the correct OrderExecutionPort for an account.

        Args:
            account_id: Account identifier (e.g., ``"dhan/default"``).

        Returns:
            OrderExecutionPort implementation.

        Raises:
            BrokerError: If account_id is invalid or broker is not registered.
        """
        broker_id = self._parse_account_id(account_id)
        with self._lock:
            adapter = self._adapters.get(broker_id)
        if adapter is None:
            raise BrokerError(
                f"No execution adapter registered for broker {broker_id!r} "
                f"(from account_id {account_id!r}). "
                f"Registered brokers: {list(self._adapters.keys())}"
            )
        return adapter

    # ── Delegation Methods ─────────────────────────────────────────────

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
    ) -> OrderResponse:
        """Place an order, routing to the correct broker by account.

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

        Returns:
            OrderResponse from the broker adapter.
        """
        adapter = self.route(account_id)
        return adapter.place_order(
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

    def modify_order(
        self,
        account_id: str,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        order_type: OrderType | None = None,
        validity: Validity | None = None,
    ) -> OrderResponse:
        """Modify an order, routing to the correct broker by account.

        Args:
            account_id: Account identifier for routing.
            order_id: Order identifier to modify.
            quantity: New quantity (optional).
            price: New price (optional).
            order_type: New order type (optional).
            validity: New validity (optional).

        Returns:
            OrderResponse from the broker adapter.
        """
        adapter = self.route(account_id)
        return adapter.modify_order(
            order_id=order_id,
            quantity=quantity,
            price=price,
            order_type=order_type,
            validity=validity,
        )

    def cancel_order(self, account_id: str, order_id: str) -> OrderResponse:
        """Cancel an order, routing to the correct broker by account.

        Args:
            account_id: Account identifier for routing.
            order_id: Order identifier to cancel.

        Returns:
            OrderResponse from the broker adapter.
        """
        adapter = self.route(account_id)
        return adapter.cancel_order(order_id)

    def get_order(self, account_id: str, order_id: str) -> Order | None:
        """Get order details, routing to the correct broker by account.

        Args:
            account_id: Account identifier for routing.
            order_id: Order identifier.

        Returns:
            Order if found, None otherwise.
        """
        adapter = self.route(account_id)
        return adapter.get_order(order_id)

    def get_orderbook(self, account_id: str) -> list[Order]:
        """Get all orders for an account, routing to the correct broker.

        Args:
            account_id: Account identifier for routing.

        Returns:
            List of Order objects.
        """
        adapter = self.route(account_id)
        return adapter.get_orderbook()

    def __repr__(self) -> str:
        with self._lock:
            brokers = list(self._adapters.keys())
        return f"ExecutionRouter(brokers={brokers})"

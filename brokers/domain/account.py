"""Account — execution aggregate root.

Owns order placement, positions, holdings, and balance.
Risk gating happens HERE, inside ``place_order`` — not in a wrapper.

This is a rich domain object.  The risk policy is injected as a
Strategy, not wrapped around the account.  The domain layer defines
its own Protocol for the risk policy to maintain domain purity
(no imports from ``brokers.risk``).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from brokers.domain.order import Order
from brokers.domain.requests import ModifyOrderRequest, OrderRequest
from brokers.domain.values import Balance, Holding, OrderResponse, Position, Subscription, Trade

if TYPE_CHECKING:
    from brokers.infrastructure.event_bus import EventBus
    from brokers.provider.protocol import ExecutionProvider


# ── Domain-local protocols (maintain domain purity) ────────────────────────


@dataclass(frozen=True, slots=True)
class RiskDecision:
    """Result of a risk policy check — defined in domain for purity."""

    allowed: bool
    rule: str = ""
    value: Decimal = Decimal("0")
    limit: Decimal = Decimal("0")
    reason: str = ""
    error_code: str = ""

    @staticmethod
    def allow() -> RiskDecision:
        return RiskDecision(allowed=True)

    @staticmethod
    def deny(
        rule: str,
        value: Decimal,
        limit: Decimal,
        reason: str = "",
        error_code: str = "RISK_DENIED",
    ) -> RiskDecision:
        return RiskDecision(
            allowed=False,
            rule=rule,
            value=value,
            limit=limit,
            reason=reason or f"{rule}: {value} exceeds limit {limit}",
            error_code=error_code,
        )


@runtime_checkable
class RiskPolicyProtocol(Protocol):
    """Domain-local protocol for risk policies.

    The concrete ``RiskPolicy`` in ``brokers.risk`` implements this
    protocol.  By defining it here, the domain layer does not depend
    on ``brokers.risk`` — preserving domain purity.
    """

    async def check(
        self,
        request: OrderRequest,
        provider: ExecutionProvider,
    ) -> RiskDecision:
        """Check if an order request is allowed."""
        ...


class Account:
    """Aggregate root for the execution domain.

    Owns order placement, positions, holdings, and balance.
    Risk gating happens HERE — not in a wrapper.

    Usage::

        broker = Broker.dhan(client_id="123", access_token="tok")
        account = broker.account()
        response = await account.place_order(OrderRequest(...))
        positions = await account.get_positions()
    """

    __slots__ = (
        "_account_id",
        "_event_bus",
        "_lock",
        "_open_orders",
        "_provider",
        "_risk_policy",
    )

    def __init__(
        self,
        account_id: str,
        provider: ExecutionProvider,
        *,
        risk_policy: RiskPolicyProtocol | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._account_id = account_id
        self._provider = provider
        self._risk_policy = risk_policy  # May be None = no limits
        self._event_bus = event_bus
        self._lock = threading.RLock()
        self._open_orders: dict[str, Order] = {}

    # ── Identity ─────────────────────────────────────────────────────

    @property
    def account_id(self) -> str:
        return self._account_id

    @property
    def provider(self) -> ExecutionProvider:
        return self._provider

    @property
    def risk_policy(self) -> RiskPolicyProtocol | None:
        return self._risk_policy

    # ── Order placement (risk gating happens HERE) ───────────────────

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        """Place an order with risk gating.

        Risk check happens HERE — not in a wrapper.  If denied, returns
        ``OrderResponse.fail()`` with the reason.

        Flow:
        1. Risk policy check (Strategy, not wrapper)
        2. Execute via provider
        3. Track order in _open_orders (real state management)
        4. Publish ORDER_PLACED event (real responsibility)
        """
        # Risk gate — real responsibility, not a forwarding wrapper
        if self._risk_policy is not None:
            decision = await self._risk_policy.check(request, self._provider)
            if not decision.allowed:
                # Publish RISK_REJECTED event
                if self._event_bus is not None:
                    from brokers.domain.events import DomainEvent

                    self._event_bus.publish(
                        DomainEvent.now(
                            event_type="RISK_REJECTED",
                            payload={
                                "order_id": "",
                                "rule": decision.rule,
                                "value": str(decision.value),
                                "limit": str(decision.limit),
                                "reason": decision.reason,
                            },
                            symbol=request.symbol,
                        )
                    )
                return OrderResponse.fail(
                    f"Risk denied: {decision.reason}",
                    error_code=decision.error_code,
                )

        # Execute — delegate to provider
        response = await self._provider.place_order(request)

        # Track order — real state management
        if response.success:
            order = Order.from_response(request, response)
            with self._lock:
                self._open_orders[response.order_id] = order

            # Publish ORDER_PLACED event
            if self._event_bus is not None:
                from brokers.domain.events import DomainEvent

                self._event_bus.publish(
                    DomainEvent.now(
                        event_type="ORDER_PLACED",
                        payload={
                            "order_id": response.order_id,
                            "symbol": request.symbol,
                            "side": request.side.value,
                            "quantity": request.quantity,
                            "order_type": request.order_type.value,
                        },
                        symbol=request.symbol,
                    )
                )

        return response

    async def cancel_order(self, order_id: str) -> OrderResponse:
        """Cancel an open order."""
        response = await self._provider.cancel_order(order_id)

        # Update tracked order status
        if response.success:
            with self._lock:
                order = self._open_orders.get(order_id)
                if order is not None:
                    from brokers.domain.enums import OrderStatus

                    order.update_status(
                        OrderStatus.CANCELLED,
                        event_bus=self._event_bus,
                    )

        return response

    async def modify_order(self, request: ModifyOrderRequest) -> OrderResponse:
        """Modify an open order."""
        return await self._provider.modify_order(request)

    # ── Portfolio queries (delegate to provider) ─────────────────────

    async def get_positions(self) -> list[Position]:
        """Return all open positions."""
        return await self._provider.get_positions()

    async def get_balance(self) -> Balance:
        """Return account balance and margin usage."""
        return await self._provider.get_balance()

    async def get_orders(self) -> list[Any]:
        """Return current order book."""
        return await self._provider.get_orders()

    async def get_trades(self) -> list[Trade]:
        """Return today's executed trades."""
        return await self._provider.get_trades()

    async def get_holdings(self) -> list[Holding]:
        """Return long-term equity holdings."""
        return await self._provider.get_holdings()

    # ── Streaming ────────────────────────────────────────────────────

    async def subscribe_orders(
        self, *, on_update: Callable[[Any], None] | None = None
    ) -> Subscription:
        """Subscribe to order status updates."""
        from brokers.provider.protocol import StreamingProvider

        if not isinstance(self._provider, StreamingProvider):
            raise TypeError(
                f"Provider {self._provider.broker_id!r} does not support streaming."
            )
        return await self._provider.subscribe_orders(on_update=on_update)

    # ── Tracked orders (local state) ─────────────────────────────────

    @property
    def open_orders(self) -> dict[str, Order]:
        """Snapshot of locally tracked open orders."""
        with self._lock:
            return dict(self._open_orders)

    def get_tracked_order(self, order_id: str) -> Order | None:
        """Get a locally tracked order by ID."""
        with self._lock:
            return self._open_orders.get(order_id)

    def __repr__(self) -> str:
        return f"Account({self._account_id}, {self._provider.broker_id})"


__all__ = ["Account", "RiskDecision", "RiskPolicyProtocol"]

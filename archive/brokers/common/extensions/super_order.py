"""SuperOrderProvider extension interface.

Capability gate: ``BrokerCapabilities.supports_super_order``
Supported by: Dhan (native API — entry + target + stop-loss + trailing)
Not supported by: Upstox (emulation only via multi-leg, not exposed here)

Dhan super orders are a single-API-call bracket: one entry leg plus target and
stop-loss legs managed server-side.  The failure mode is a single atomic reject,
not leg desynchronization — unlike client-side emulation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from brokers.common.broker_port import QuotaToken
from domain.enums import OrderStatus, OrderType, ProductType, Side, Validity


@dataclass(frozen=True)
class SuperOrderRequest:
    """Input for placing a Dhan-style super (bracket) order.

    entry_price       — limit price for the entry leg.
    target_price      — target take-profit price.
    stop_loss_price   — stop-loss trigger price.
    trailing_jump     — trailing stop-loss jump amount; 0 disables trailing.
    quantity          — number of lots/shares.
    """

    symbol: str
    exchange: str
    side: Side
    quantity: int
    entry_price: Decimal
    target_price: Decimal
    stop_loss_price: Decimal
    order_type: OrderType = OrderType.LIMIT
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    trailing_jump: Decimal = Decimal("0")
    correlation_id: str | None = None


@dataclass(frozen=True)
class SuperOrderResult:
    """Result of a super order placement.

    All three leg IDs are returned by the broker on success.
    """

    success: bool
    entry_order_id: str = ""
    target_order_id: str = ""
    stop_loss_order_id: str = ""
    message: str = ""
    status: OrderStatus = OrderStatus.OPEN


class SuperOrderProvider(Protocol):
    """Extension interface for Dhan-native bracket orders.

    Use ``ExtensionRegistry.require(broker_id, SuperOrderProvider)`` to obtain
    this; Upstox will raise ``UnsupportedExtensionError``.
    """

    async def place_super_order(
        self,
        request: SuperOrderRequest,
        *,
        quota: QuotaToken,
    ) -> SuperOrderResult:
        """Place a bracket order returning all three leg IDs."""
        ...

    async def cancel_super_order(
        self,
        entry_order_id: str,
        *,
        quota: QuotaToken,
    ) -> SuperOrderResult:
        """Cancel all legs of a bracket order by the entry order ID."""
        ...

    async def modify_super_order(
        self,
        entry_order_id: str,
        *,
        target_price: Decimal | None = None,
        stop_loss_price: Decimal | None = None,
        trailing_jump: Decimal | None = None,
        quota: QuotaToken,
    ) -> SuperOrderResult:
        """Modify target/SL/trailing of an existing super order."""
        ...

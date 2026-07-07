"""Value objects — immutable dataclasses for market data and execution state.

These are the canonical output types for all provider operations.
Every value object is frozen (immutable) for thread safety, except
:class:`Subscription` which has mutable ``_active`` state.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from brokers.domain.enums import Exchange, OrderStatus, ProductType, Side

if TYPE_CHECKING:
    pass


# ── Market data value objects ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Quote:
    """Point-in-time market quote (LTP + OHLCV)."""

    symbol: str
    ltp: Decimal
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    volume: int = 0
    change: Decimal = Decimal("0")
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class DepthLevel:
    """Single bid/ask level in an order book."""

    price: Decimal
    quantity: int
    orders: int = 0


@dataclass(frozen=True, slots=True)
class MarketDepth:
    """Order book depth snapshot."""

    symbol: str
    bids: list[DepthLevel] = field(default_factory=list)
    asks: list[DepthLevel] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    depth_type: str = "DEPTH_20"


# ── Execution value objects ────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Position:
    """Open position for a single instrument."""

    symbol: str
    exchange: Exchange
    quantity: int
    average_price: Decimal
    ltp: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    product_type: ProductType = ProductType.INTRADAY
    correlation_id: str | None = None

    @property
    def pnl(self) -> Decimal:
        """Total P&L (unrealized + realized)."""
        return self.unrealized_pnl + self.realized_pnl

    @property
    def is_long(self) -> bool:
        return self.quantity > 0

    @property
    def is_short(self) -> bool:
        return self.quantity < 0

    @property
    def is_flat(self) -> bool:
        return self.quantity == 0

    def with_ltp(self, ltp: Decimal) -> Position:
        """Return a new Position with updated LTP and unrealized P&L."""
        if self.quantity > 0:
            unrealized = Decimal(str(self.quantity)) * (ltp - self.average_price)
        elif self.quantity < 0:
            unrealized = Decimal(str(abs(self.quantity))) * (self.average_price - ltp)
        else:
            unrealized = Decimal("0")
        return replace(self, ltp=ltp, unrealized_pnl=unrealized)


@dataclass(frozen=True, slots=True)
class Balance:
    """Account balance and margin snapshot."""

    available_balance: Decimal
    used_margin: Decimal = Decimal("0")
    total_value: Decimal = Decimal("0")
    sod_limit: Decimal = Decimal("0")
    collateral_amount: Decimal = Decimal("0")
    withdrawable_balance: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class Trade:
    """Canonical trade — an executed fill."""

    trade_id: str
    order_id: str
    symbol: str
    exchange: Exchange
    side: Side
    quantity: int
    price: Decimal = Decimal("0")
    timestamp: datetime | None = None
    product_type: ProductType = ProductType.INTRADAY
    correlation_id: str | None = None

    @property
    def value(self) -> Decimal:
        """Total trade value (price × quantity)."""
        return self.price * Decimal(str(self.quantity))


@dataclass(frozen=True, slots=True)
class Holding:
    """Long-term equity holding (CNC delivery)."""

    symbol: str
    exchange: Exchange
    quantity: int = 0
    available_quantity: int = 0
    average_price: Decimal = Decimal("0")
    ltp: Decimal = Decimal("0")
    pnl: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class Greeks:
    """Typed option Greeks — replaces ``dict[str, Any]``.

    Each greek is optional because not all providers compute all five.
    """

    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> Greeks:
        """Build from a flat dict with delta/theta/gamma/vega/rho keys."""
        if not data:
            return cls()
        return cls(
            delta=_dec(data.get("delta")),
            gamma=_dec(data.get("gamma")),
            theta=_dec(data.get("theta")),
            vega=_dec(data.get("vega")),
            rho=_dec(data.get("rho")),
        )


@dataclass(frozen=True, slots=True)
class OrderResponse:
    """Result of an order placement / cancellation / modification.

    Following the v2 principle: use native exceptions for infrastructure
    errors and ``OrderResponse`` for business outcomes (success/rejection).
    """

    success: bool
    order_id: str = ""
    message: str = ""
    status: OrderStatus = OrderStatus.OPEN
    error_code: str = ""

    @classmethod
    def ok(
        cls,
        *,
        order_id: str = "",
        message: str = "OK",
        status: OrderStatus = OrderStatus.OPEN,
    ) -> OrderResponse:
        return cls(success=True, order_id=order_id, message=message, status=status)

    @classmethod
    def fail(cls, message: str, *, error_code: str = "") -> OrderResponse:
        return cls(
            success=False,
            message=message,
            status=OrderStatus.REJECTED,
            error_code=error_code,
        )


# ── Subscription handle ────────────────────────────────────────────────────


class Subscription:
    """Handle for an active stream subscription.

    Created by the provider when subscribing to quotes, depth, or order
    updates.  Call ``cancel()`` to unsubscribe.

    Not frozen — ``_active`` is mutable state.  Thread-safe via a lock.
    """

    __slots__ = ("_active", "_cancel_fn", "_id", "_lock")

    def __init__(
        self,
        subscription_id: str,
        cancel_fn: Callable[[], Awaitable[None]],
    ) -> None:
        self._id = subscription_id
        self._cancel_fn = cancel_fn
        self._active = True
        self._lock = threading.Lock()

    @property
    def subscription_id(self) -> str:
        return self._id

    @property
    def is_active(self) -> bool:
        with self._lock:
            return self._active

    async def cancel(self) -> None:
        """Cancel the subscription. Idempotent — safe to call multiple times."""
        with self._lock:
            if not self._active:
                return
            self._active = False
        await self._cancel_fn()

    @staticmethod
    def create_id() -> str:
        """Generate a unique subscription ID."""
        return uuid.uuid4().hex[:12]


# ── Parsing helpers ────────────────────────────────────────────────────────


def _dec(val: object) -> Decimal | None:
    """Parse a value to Decimal, returning None for missing/empty values."""
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except (ValueError, TypeError):
        return None


__all__ = [
    "Balance",
    "DepthLevel",
    "Greeks",
    "Holding",
    "MarketDepth",
    "OrderResponse",
    "Position",
    "Quote",
    "Subscription",
    "Trade",
]

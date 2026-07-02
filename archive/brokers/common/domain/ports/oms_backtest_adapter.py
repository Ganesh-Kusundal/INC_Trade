"""OMS backtest adapter protocol for analytics engines.

Expanded port with modify/cancel/query methods for full
backtest-live parity.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OmsBacktestAdapterPort(Protocol):
    """Port for simulated OMS fills in paper/replay/backtest engines.

    Implementations route order lifecycle through the OMS so that
    backtest, paper, and live trading share identical risk checks,
    idempotency guards, and event publishing.
    """

    def open_long(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        price: Decimal,
        timestamp: datetime,
        *,
        strategy: str | None = None,
        reasons: list[str] | None = None,
    ) -> str | None:
        """Open a long position. Returns order_id on success, None on rejection."""
        ...

    def close_long(
        self,
        symbol: str,
        exchange: str,
        quantity: int,
        price: Decimal,
        timestamp: datetime,
        *,
        strategy: str | None = None,
        reasons: list[str] | None = None,
    ) -> str | None:
        """Close a long position. Returns order_id on success, None on rejection."""
        ...

    def modify_order(
        self,
        order_id: str,
        *,
        price: Decimal | None = None,
        quantity: int | None = None,
        trigger_price: Decimal | None = None,
    ) -> bool:
        """Modify an open order. Returns True if modification accepted."""
        ...

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Returns True if cancellation accepted."""
        ...

    def get_position(self, symbol: str, exchange: str = "NSE") -> dict[str, Any] | None:
        """Return current position for a symbol, or None if flat.

        Returns dict with keys: symbol, exchange, quantity, avg_price, ltp,
        unrealized_pnl, realized_pnl.
        """
        ...

    def get_orders(self) -> list[dict[str, Any]]:
        """Return all orders placed through this adapter."""
        ...


__all__ = ["OmsBacktestAdapterPort"]

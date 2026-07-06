"""Order guard port — single choke point for live-order safety checks."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from brokers.domain.entities import OrderResponse


@runtime_checkable
class OrderGuardPort(Protocol):
    """Blocks place/modify/cancel when live trading is disabled."""

    def check_live_order_allowed(self) -> OrderResponse | None:
        """Return a failure response when blocked, or None when allowed."""
        ...

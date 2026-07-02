"""Shared execution math for analytics engines."""

from __future__ import annotations


def compute_order_quantity(
    *,
    equity: float,
    price: float,
    max_position_pct: float,
) -> int:
    if price <= 0 or equity <= 0 or max_position_pct <= 0:
        return 0
    max_notional = equity * (max_position_pct / 100.0)
    return max(0, int(max_notional / price))


__all__ = ["compute_order_quantity"]

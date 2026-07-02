"""Shared order validation utilities (REF-06 extraction).

Contains lightweight, stateless validation helpers that were previously
duplicated across broker adapters.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def high_notional_warning(
    quantity: int,
    price: Decimal | Any | None,
    threshold: Decimal = Decimal("50000"),
) -> list[str]:
    """Return a warning list if the order notional exceeds *threshold*.

    Parameters
    ----------
    quantity
        Order quantity.
    price
        Order price (may be None for market orders).
    threshold
        Notional threshold in rupees (default ₹50 000).

    Returns
    -------
    list[str]
        Non-empty if the notional exceeds the threshold.
    """
    warnings: list[str] = []
    if price and price > 0:
        notional = Decimal(str(quantity)) * Decimal(str(price))
        if notional > threshold:
            warnings.append(
                f"High notional: ₹{notional:,.0f} exceeds ₹{threshold:,.0f} threshold"
            )
    return warnings

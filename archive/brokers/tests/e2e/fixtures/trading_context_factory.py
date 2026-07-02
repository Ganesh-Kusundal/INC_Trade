"""Factory for paper-trading test contexts."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def create_paper_trading_context(
    capital: Decimal = Decimal("1000000"),
    max_position_pct: Decimal = Decimal("25"),
    max_gross_pct: Decimal = Decimal("100"),
    max_daily_loss_pct: Decimal = Decimal("5"),
    **kwargs: Any,
) -> dict[str, Any]:
    """Create a paper trading context dict for testing."""
    return {
        "capital": capital,
        "max_position_pct": max_position_pct,
        "max_gross_pct": max_gross_pct,
        "max_daily_loss_pct": max_daily_loss_pct,
        "broker": "paper",
        **kwargs,
    }

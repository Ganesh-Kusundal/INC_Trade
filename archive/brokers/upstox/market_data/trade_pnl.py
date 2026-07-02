"""Trade P&L calculator for Upstox.

Calculates realized and unrealized P&L from positions and trades.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TradePnL:
    """Trade profit and loss calculation result."""

    symbol: str
    exchange: str
    quantity: int
    average_price: Decimal
    current_price: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    pnl_percentage: Decimal


class TradePnLCalculator:
    """Calculate trade P&L from positions and current market prices."""

    def __init__(self, portfolio_client: Any, market_data_client: Any) -> None:
        self._portfolio = portfolio_client
        self._market_data = market_data_client

    def calculate_all_pnl(self) -> list[TradePnL]:
        """Calculate P&L for all current positions."""
        positions = self._portfolio.get_short_term_positions()
        pnl_results = []

        for pos_data in positions:
            pnl = self._calculate_position_pnl(pos_data)
            if pnl is not None:
                pnl_results.append(pnl)

        return pnl_results

    def _calculate_position_pnl(self, pos_data: dict[str, Any]) -> TradePnL | None:
        """Calculate P&L for a single position."""
        if not isinstance(pos_data, dict):
            return None

        symbol = pos_data.get("trading_symbol", "")
        exchange = pos_data.get("exchange", "")
        quantity = int(pos_data.get("quantity", 0))
        average_price = Decimal(str(pos_data.get("average_price", 0)))

        if quantity == 0:
            return None

        # Get current market price
        current_price = self._get_current_price(pos_data)

        # Calculate unrealized P&L
        price_diff = current_price - average_price
        unrealized_pnl = price_diff * quantity

        # For simplicity, realized P&L is 0 (would require trade history)
        realized_pnl = Decimal("0")
        total_pnl = unrealized_pnl

        # Calculate percentage
        pnl_percentage = (
            (price_diff / average_price * Decimal("100")) if average_price > 0 else Decimal("0")
        )

        return TradePnL(
            symbol=symbol,
            exchange=exchange,
            quantity=quantity,
            average_price=average_price,
            current_price=current_price,
            realized_pnl=realized_pnl,
            unrealized_pnl=unrealized_pnl,
            total_pnl=total_pnl,
            pnl_percentage=pnl_percentage,
        )

    def _get_current_price(self, pos_data: dict[str, Any]) -> Decimal:
        """Get current market price for a position."""
        instrument_key = pos_data.get("instrument_key", "")
        if not instrument_key:
            return Decimal(str(pos_data.get("last_price", 0)))

        try:
            # Try to get LTP from market data
            ltp_body = self._market_data.get_ltp([instrument_key])
            data = ltp_body.get("data", {})
            if instrument_key in data:
                return Decimal(str(data[instrument_key].get("last_price", 0)))
        except Exception as exc:
            # Fallback to last_price from position data
            logger.warning(
                "trade_pnl_market_data_error",
                extra={
                    "instrument_key": instrument_key,
                    "error": str(exc),
                    "fallback": "using_last_price_from_position",
                },
            )

        return Decimal(str(pos_data.get("last_price", 0)))

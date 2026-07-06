"""Portfolio aggregator — net exposure across positions and holdings.

Pure-function utilities that operate on lists of ``Position`` and
``Holding`` entities. No broker or HTTP coupling.

Used by:
- Risk management
- Strategy analytics
- Dashboard summaries
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from brokers.domain.entities import Holding, Position


@dataclass
class ExposureSummary:
    """Aggregated portfolio exposure metrics.

    Attributes:
        total_positions: Number of positions.
        total_holdings: Number of holdings.
        net_quantity: Sum of net position quantities (positive = long).
        gross_exposure: Sum of abs(position.quantity * price).
        net_exposure: Sum of signed(position.quantity * price).
        unrealized_pnl: Sum of position.unrealized_pnl.
        realized_pnl: Sum of position.realized_pnl.
        long_quantity: Total long quantity.
        short_quantity: Total short quantity (positive value).
        by_symbol: Per-symbol net exposure.
    """

    total_positions: int = 0
    total_holdings: int = 0
    net_quantity: int = 0
    gross_exposure: Decimal = Decimal("0")
    net_exposure: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    long_quantity: int = 0
    short_quantity: int = 0
    by_symbol: dict[str, Decimal] | None = None


class PortfolioAggregator:
    """Aggregate positions, holdings, and trades.

    Pure functions — no state, no side effects. Reusable across
    strategies and dashboards.
    """

    @staticmethod
    def aggregate_positions(
        positions: Iterable[Position],
    ) -> ExposureSummary:
        """Aggregate a list of positions into a single summary.

        Args:
            positions: Iterable of ``Position`` domain entities.

        Returns:
            ``ExposureSummary`` with totals and per-symbol breakdown.
        """
        by_symbol: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        gross = Decimal("0")
        net_exposure = Decimal("0")
        unrealized = Decimal("0")
        realized = Decimal("0")
        net_qty = 0
        long_qty = 0
        short_qty = 0
        count = 0
        for p in positions:
            count += 1
            qty = p.quantity
            net_qty += qty
            if qty > 0:
                long_qty += qty
            elif qty < 0:
                short_qty += abs(qty)
            signed_value = Decimal(qty) * p.average_price
            gross += abs(signed_value)
            net_exposure += signed_value
            by_symbol[f"{p.exchange}:{p.symbol}"] += signed_value
            unrealized += p.unrealized_pnl
            realized += p.realized_pnl
        return ExposureSummary(
            total_positions=count,
            net_quantity=net_qty,
            gross_exposure=gross,
            net_exposure=net_exposure,
            unrealized_pnl=unrealized,
            realized_pnl=realized,
            long_quantity=long_qty,
            short_quantity=short_qty,
            by_symbol=dict(by_symbol),
        )

    @staticmethod
    def aggregate_holdings(holdings: Iterable[Holding]) -> ExposureSummary:
        """Aggregate holdings (delivery positions).

        Args:
            holdings: Iterable of ``Holding`` domain entities.

        Returns:
            ``ExposureSummary`` with holdings totals.
        """
        count = 0
        net_qty = 0
        for h in holdings:
            count += 1
            net_qty += h.quantity
        return ExposureSummary(
            total_holdings=count,
            net_quantity=net_qty,
        )

    @staticmethod
    def net_exposure_by_symbol(
        positions: Iterable[Position],
    ) -> dict[str, Decimal]:
        """Per-symbol net exposure (signed).

        Args:
            positions: Iterable of ``Position``.

        Returns:
            Dict mapping ``{exchange}:{symbol}`` to net signed exposure.
        """
        out: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for p in positions:
            out[f"{p.exchange}:{p.symbol}"] += Decimal(p.quantity) * p.average_price
        return dict(out)

"""Unit tests for PortfolioAggregator."""

from __future__ import annotations

from decimal import Decimal

from inc_trade.domain.entities import Holding, Position
from brokers.trading.portfolio import ExposureSummary, PortfolioAggregator


def _position(
    symbol: str,
    exchange: str,
    qty: int,
    avg_price: Decimal,
    unrealized: Decimal = Decimal("0"),
    realized: Decimal = Decimal("0"),
) -> Position:
    return Position(
        symbol=symbol,
        exchange=exchange,
        quantity=qty,
        average_price=avg_price,
        unrealized_pnl=unrealized,
        realized_pnl=realized,
    )


class TestPortfolioAggregator:
    def test_empty_positions(self) -> None:
        summary = PortfolioAggregator.aggregate_positions([])
        assert summary.total_positions == 0
        assert summary.net_quantity == 0
        assert summary.gross_exposure == Decimal("0")
        assert summary.unrealized_pnl == Decimal("0")

    def test_single_long_position(self) -> None:
        positions = [_position("RELIANCE", "NSE", 100, Decimal("2500"), unrealized=Decimal("500"))]
        s = PortfolioAggregator.aggregate_positions(positions)
        assert s.total_positions == 1
        assert s.long_quantity == 100
        assert s.short_quantity == 0
        assert s.gross_exposure == Decimal("250000")
        assert s.net_exposure == Decimal("250000")
        assert s.unrealized_pnl == Decimal("500")

    def test_single_short_position(self) -> None:
        positions = [_position("TCS", "NSE", -50, Decimal("3000"))]
        s = PortfolioAggregator.aggregate_positions(positions)
        assert s.short_quantity == 50
        assert s.net_quantity == -50
        assert s.gross_exposure == Decimal("150000")
        assert s.net_exposure == Decimal("-150000")

    def test_mixed_long_short(self) -> None:
        positions = [
            _position("A", "NSE", 100, Decimal("10")),
            _position("B", "NSE", -50, Decimal("20")),
        ]
        s = PortfolioAggregator.aggregate_positions(positions)
        assert s.gross_exposure == Decimal("1000") + Decimal("1000")
        assert s.net_exposure == Decimal("1000") - Decimal("1000")
        assert s.long_quantity == 100
        assert s.short_quantity == 50

    def test_pnl_aggregation(self) -> None:
        positions = [
            _position(
                "A", "NSE", 10, Decimal("100"), unrealized=Decimal("50"), realized=Decimal("20")
            ),
            _position(
                "B", "NSE", 20, Decimal("200"), unrealized=Decimal("-30"), realized=Decimal("10")
            ),
        ]
        s = PortfolioAggregator.aggregate_positions(positions)
        assert s.unrealized_pnl == Decimal("20")
        assert s.realized_pnl == Decimal("30")

    def test_by_symbol_breakdown(self) -> None:
        positions = [
            _position("RELIANCE", "NSE", 100, Decimal("2500")),
            _position("RELIANCE", "BSE", 50, Decimal("2510")),  # different exchange
        ]
        s = PortfolioAggregator.aggregate_positions(positions)
        assert "NSE:RELIANCE" in s.by_symbol
        assert "BSE:RELIANCE" in s.by_symbol
        assert s.by_symbol["NSE:RELIANCE"] == Decimal("250000")
        assert s.by_symbol["BSE:RELIANCE"] == Decimal("125500")

    def test_net_exposure_by_symbol(self) -> None:
        positions = [
            _position("X", "NSE", 10, Decimal("100")),
            _position("Y", "NSE", 20, Decimal("50")),
        ]
        out = PortfolioAggregator.net_exposure_by_symbol(positions)
        assert out["NSE:X"] == Decimal("1000")
        assert out["NSE:Y"] == Decimal("1000")

    def test_holdings_aggregation(self) -> None:
        holdings = [
            Holding(symbol="RELIANCE", exchange="NSE", quantity=100, average_price=Decimal("2500")),
            Holding(symbol="TCS", exchange="NSE", quantity=50, average_price=Decimal("3000")),
        ]
        s = PortfolioAggregator.aggregate_holdings(holdings)
        assert s.total_holdings == 2
        assert s.net_quantity == 150


class TestExposureSummary:
    def test_default_values(self) -> None:
        s = ExposureSummary()
        assert s.total_positions == 0
        assert s.net_exposure == Decimal("0")

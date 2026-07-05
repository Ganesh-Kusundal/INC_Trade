"""Unit tests for ``Instrument.aggregate_positions`` and ``AggregatedExposure``."""

from __future__ import annotations

from decimal import Decimal

import pytest

from inc_trade.domain.entities import AggregatedExposure, Position
from inc_trade.market import AggregatedExposure as MarketAggregatedExposure
from inc_trade.market import Instrument
from inc_trade.market.instrument import Instrument as DirectInstrument


def _pos(
    symbol: str,
    exchange: str,
    qty: int,
    avg_price: Decimal = Decimal("100"),
) -> Position:
    return Position(
        symbol=symbol,
        exchange=exchange,
        quantity=qty,
        average_price=avg_price,
    )


class TestAggregatedExposureValueObject:
    """Sanity tests for the new domain value object itself."""

    def test_is_flat_true_when_net_zero(self) -> None:
        agg = AggregatedExposure(
            symbol="RELIANCE",
            exchange="NSE",
            net_quantity=0,
            gross_quantity=20,
            long_quantity=10,
            short_quantity=10,
            position_count=2,
        )
        assert agg.is_flat is True

    def test_is_flat_false_when_net_positive(self) -> None:
        agg = AggregatedExposure(
            symbol="RELIANCE",
            exchange="NSE",
            net_quantity=5,
            gross_quantity=5,
            long_quantity=5,
            short_quantity=0,
            position_count=1,
        )
        assert agg.is_flat is False

    def test_is_flat_false_when_net_negative(self) -> None:
        agg = AggregatedExposure(
            symbol="RELIANCE",
            exchange="NSE",
            net_quantity=-3,
            gross_quantity=3,
            long_quantity=0,
            short_quantity=3,
            position_count=1,
        )
        assert agg.is_flat is False

    def test_is_frozen(self) -> None:
        agg = AggregatedExposure(
            symbol="RELIANCE",
            exchange="NSE",
            net_quantity=0,
            gross_quantity=0,
            long_quantity=0,
            short_quantity=0,
            position_count=0,
        )
        with pytest.raises(Exception):
            agg.net_quantity = 5  # type: ignore[misc]

    def test_market_module_reexports_aggregated_exposure(self) -> None:
        # Same class identity, no surprises
        assert MarketAggregatedExposure is AggregatedExposure
        assert DirectInstrument is Instrument


class TestAggregatePositionsEmpty:
    def test_empty_list_returns_zero_exposure(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        agg = inst.aggregate_positions([])
        assert agg.symbol == "RELIANCE"
        assert agg.exchange == "NSE"
        assert agg.net_quantity == 0
        assert agg.gross_quantity == 0
        assert agg.long_quantity == 0
        assert agg.short_quantity == 0
        assert agg.position_count == 0
        assert agg.is_flat is True

    def test_no_matching_positions_returns_zero_exposure(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        positions = [
            _pos("TCS", "NSE", 10),
            _pos("INFY", "BSE", 5),
        ]
        agg = inst.aggregate_positions(positions)
        assert agg.net_quantity == 0
        assert agg.gross_quantity == 0
        assert agg.long_quantity == 0
        assert agg.short_quantity == 0
        assert agg.position_count == 0
        assert agg.is_flat is True


class TestAggregatePositionsSingleSide:
    def test_single_long_position(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        positions = [_pos("RELIANCE", "NSE", 10)]
        agg = inst.aggregate_positions(positions)
        assert agg.symbol == "RELIANCE"
        assert agg.exchange == "NSE"
        assert agg.net_quantity == 10
        assert agg.gross_quantity == 10
        assert agg.long_quantity == 10
        assert agg.short_quantity == 0
        assert agg.position_count == 1
        assert agg.is_flat is False

    def test_single_short_position(self) -> None:
        inst = Instrument(symbol="TCS", exchange="NSE")
        positions = [_pos("TCS", "NSE", -5)]
        agg = inst.aggregate_positions(positions)
        assert agg.net_quantity == -5
        assert agg.gross_quantity == 5
        assert agg.long_quantity == 0
        assert agg.short_quantity == 5
        assert agg.position_count == 1
        assert agg.is_flat is False


class TestAggregatePositionsMixed:
    def test_long_10_plus_short_3(self) -> None:
        inst = Instrument(symbol="NIFTY", exchange="NFO")
        positions = [
            _pos("NIFTY", "NFO", 10),
            _pos("NIFTY", "NFO", -3),
        ]
        agg = inst.aggregate_positions(positions)
        assert agg.net_quantity == 7
        assert agg.gross_quantity == 13
        assert agg.long_quantity == 10
        assert agg.short_quantity == 3
        assert agg.position_count == 2
        assert agg.is_flat is False

    def test_long_and_short_exactly_cancel(self) -> None:
        inst = Instrument(symbol="NIFTY", exchange="NFO")
        positions = [
            _pos("NIFTY", "NFO", 7),
            _pos("NIFTY", "NFO", -7),
        ]
        agg = inst.aggregate_positions(positions)
        assert agg.net_quantity == 0
        assert agg.gross_quantity == 14
        assert agg.long_quantity == 7
        assert agg.short_quantity == 7
        assert agg.position_count == 2
        assert agg.is_flat is True

    def test_multiple_long_positions_sum(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        positions = [
            _pos("RELIANCE", "NSE", 5),
            _pos("RELIANCE", "NSE", 12),
            _pos("RELIANCE", "NSE", 3),
        ]
        agg = inst.aggregate_positions(positions)
        assert agg.net_quantity == 20
        assert agg.gross_quantity == 20
        assert agg.long_quantity == 20
        assert agg.short_quantity == 0
        assert agg.position_count == 3

    def test_zero_quantity_position_is_counted_but_neutral(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        positions = [
            _pos("RELIANCE", "NSE", 10),
            _pos("RELIANCE", "NSE", 0),
        ]
        agg = inst.aggregate_positions(positions)
        assert agg.net_quantity == 10
        assert agg.gross_quantity == 10
        assert agg.long_quantity == 10
        assert agg.short_quantity == 0
        assert agg.position_count == 2


class TestAggregatePositionsFiltering:
    def test_other_instruments_filtered_out(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        positions = [
            _pos("RELIANCE", "NSE", 10),
            _pos("TCS", "NSE", 99),  # different symbol
            _pos("INFY", "NSE", 50),  # different symbol
        ]
        agg = inst.aggregate_positions(positions)
        assert agg.net_quantity == 10
        assert agg.long_quantity == 10
        assert agg.short_quantity == 0
        assert agg.position_count == 1

    def test_same_symbol_different_exchange_filtered_out(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        positions = [
            _pos("RELIANCE", "NSE", 10),
            _pos("RELIANCE", "BSE", 25),  # same symbol, different exchange
            _pos("RELIANCE", "NFO", 5),  # same symbol, derivative exchange
        ]
        agg = inst.aggregate_positions(positions)
        assert agg.net_quantity == 10
        assert agg.gross_quantity == 10
        assert agg.long_quantity == 10
        assert agg.short_quantity == 0
        assert agg.position_count == 1

    def test_mixed_filtered_and_matching(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        positions = [
            _pos("RELIANCE", "NSE", 7),
            _pos("RELIANCE", "NSE", -3),
            _pos("RELIANCE", "BSE", 100),  # filtered
            _pos("TCS", "NSE", 50),  # filtered
        ]
        agg = inst.aggregate_positions(positions)
        assert agg.net_quantity == 4
        assert agg.gross_quantity == 10
        assert agg.long_quantity == 7
        assert agg.short_quantity == 3
        assert agg.position_count == 2


class TestAggregatePositionsPurity:
    def test_does_not_mutate_input_sequence(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        positions = [
            _pos("RELIANCE", "NSE", 10),
            _pos("RELIANCE", "NSE", -3),
        ]
        original_first_qty = positions[0].quantity
        original_second_qty = positions[1].quantity
        inst.aggregate_positions(positions)
        assert positions[0].quantity == original_first_qty
        assert positions[1].quantity == original_second_qty

    def test_accepts_arbitrary_sequence_types(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        # Tuples should work as well as lists
        positions_tuple = (
            _pos("RELIANCE", "NSE", 10),
            _pos("RELIANCE", "NSE", -3),
        )
        agg = inst.aggregate_positions(positions_tuple)
        assert agg.net_quantity == 7
        assert agg.position_count == 2

    def test_frozen_instrument_unchanged_after_call(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        positions = [_pos("RELIANCE", "NSE", 5)]
        inst.aggregate_positions(positions)
        # Reading the same fields should still work
        assert inst.symbol == "RELIANCE"
        assert inst.exchange == "NSE"
        # And modification should still be impossible
        with pytest.raises(Exception):
            inst.symbol = "TCS"  # type: ignore[misc]

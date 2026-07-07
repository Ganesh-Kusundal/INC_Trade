"""Tests for new instrument classes: Spot, HistoricalSeries."""

from datetime import datetime, timezone
from decimal import Decimal

from tradex.domain.enums import Exchange, ExchangeSegment, InstrumentType
from tradex.domain.instruments import Spot
from tradex.domain.market_data import OHLCV, HistoricalSeries

# ---------------------------------------------------------------------------
# Helper: create an OHLCV bar
# ---------------------------------------------------------------------------


def _bar(
    ts: datetime,
    o: str = "100",
    h: str = "110",
    lo: str = "95",
    c: str = "105",
    vol: int = 1000,
) -> OHLCV:
    return OHLCV(
        timestamp=ts,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(lo),
        close=Decimal(c),
        volume=vol,
    )


# ---------------------------------------------------------------------------
# Spot tests
# ---------------------------------------------------------------------------


class TestSpot:
    def test_spot_creation_with_defaults(self):
        spot = Spot(security_id="13")
        assert spot.security_id == "13"
        assert spot.last_price == Decimal("0")
        assert spot.previous_close == Decimal("0")
        # Default instrument type should be INDEX when unknown
        assert spot.instrument_type == InstrumentType.INDEX

    def test_spot_creation_with_values(self):
        spot = Spot(
            security_id="13",
            last_price=Decimal("22500"),
            previous_close=Decimal("22400"),
        )
        assert spot.last_price == Decimal("22500")
        assert spot.previous_close == Decimal("22400")

    def test_spot_change_calculation(self):
        spot = Spot(
            security_id="13",
            last_price=Decimal("22500"),
            previous_close=Decimal("22400"),
        )
        assert spot.change == Decimal("100")

    def test_spot_change_negative(self):
        spot = Spot(
            security_id="13",
            last_price=Decimal("22300"),
            previous_close=Decimal("22400"),
        )
        assert spot.change == Decimal("-100")

    def test_spot_change_pct_calculation(self):
        spot = Spot(
            security_id="13",
            last_price=Decimal("22624"),
            previous_close=Decimal("22400"),
        )
        expected = ((Decimal("22624") - Decimal("22400")) / Decimal("22400")) * 100
        assert spot.change_pct == expected

    def test_spot_change_pct_with_zero_previous_close(self):
        spot = Spot(
            security_id="13",
            last_price=Decimal("100"),
            previous_close=Decimal("0"),
        )
        assert spot.change_pct == Decimal("0")

    def test_spot_preserves_exchange(self):
        spot = Spot(
            security_id="13",
            exchange=Exchange.INDEX,
            exchange_segment=ExchangeSegment.INDEX,
        )
        assert spot.exchange == Exchange.INDEX
        assert spot.exchange_segment == ExchangeSegment.INDEX

    def test_spot_preserves_existing_instrument_type(self):
        spot = Spot(
            security_id="13",
            instrument_type=InstrumentType.EQUITY,
            last_price=Decimal("1000"),
            previous_close=Decimal("950"),
        )
        # Should keep EQUITY, not override to INDEX
        assert spot.instrument_type == InstrumentType.EQUITY

    def test_spot_change_zero_when_equal(self):
        spot = Spot(
            security_id="13",
            last_price=Decimal("100"),
            previous_close=Decimal("100"),
        )
        assert spot.change == Decimal("0")
        assert spot.change_pct == Decimal("0")


# ---------------------------------------------------------------------------
# HistoricalSeries tests
# ---------------------------------------------------------------------------


class TestHistoricalSeries:
    def _make_series(self, count: int = 5) -> HistoricalSeries:
        bars = []
        for i in range(count):
            ts = datetime(2024, 1, 1 + i, tzinfo=timezone.utc)
            bars.append(
                _bar(
                    ts,
                    o=f"{100 + i}",
                    h=f"{110 + i}",
                    lo=f"{95 + i}",
                    c=f"{105 + i}",
                    vol=1000 * (i + 1),
                )
            )
        return HistoricalSeries(
            instrument_id="13",
            exchange="NSE",
            bars=bars,
            interval="1D",
        )

    def test_creation_with_bars(self):
        series = self._make_series(3)
        assert series.instrument_id == "13"
        assert series.exchange == "NSE"
        assert series.interval == "1D"
        assert len(series.bars) == 3

    def test_count(self):
        series = self._make_series(5)
        assert series.count == 5

    def test_count_empty(self):
        series = HistoricalSeries()
        assert series.count == 0

    def test_start_date(self):
        series = self._make_series(3)
        assert series.start_date == datetime(2024, 1, 1, tzinfo=timezone.utc)

    def test_start_date_empty(self):
        series = HistoricalSeries()
        assert series.start_date is None

    def test_end_date(self):
        series = self._make_series(3)
        assert series.end_date == datetime(2024, 1, 3, tzinfo=timezone.utc)

    def test_end_date_empty(self):
        series = HistoricalSeries()
        assert series.end_date is None

    def test_first(self):
        series = self._make_series(3)
        first = series.first
        assert first is not None
        assert first.open == Decimal("100")

    def test_first_empty(self):
        series = HistoricalSeries()
        assert series.first is None

    def test_last(self):
        series = self._make_series(3)
        last = series.last
        assert last is not None
        assert last.open == Decimal("102")

    def test_last_empty(self):
        series = HistoricalSeries()
        assert series.last is None

    def test_highs(self):
        series = self._make_series(3)
        highs = series.highs
        assert highs == [Decimal("110"), Decimal("111"), Decimal("112")]

    def test_lows(self):
        series = self._make_series(3)
        lows = series.lows
        assert lows == [Decimal("95"), Decimal("96"), Decimal("97")]

    def test_closes(self):
        series = self._make_series(3)
        closes = series.closes
        assert closes == [Decimal("105"), Decimal("106"), Decimal("107")]

    def test_volumes(self):
        series = self._make_series(3)
        volumes = series.volumes
        assert volumes == [1000, 2000, 3000]

    def test_price_range(self):
        series = self._make_series(3)
        low, high = series.price_range
        assert low == Decimal("95")  # min of lows
        assert high == Decimal("112")  # max of highs

    def test_price_range_empty(self):
        series = HistoricalSeries()
        assert series.price_range == (Decimal("0"), Decimal("0"))

    def test_total_volume(self):
        series = self._make_series(3)
        assert series.total_volume == 6000  # 1000 + 2000 + 3000

    def test_total_volume_empty(self):
        series = HistoricalSeries()
        assert series.total_volume == 0

    def test_slice_sub_series(self):
        series = self._make_series(5)
        sub = series.slice(1, 4)
        assert sub.count == 3
        assert sub.instrument_id == "13"
        assert sub.exchange == "NSE"
        assert sub.interval == "1D"

    def test_slice_from_beginning(self):
        series = self._make_series(5)
        sub = series.slice(0, 2)
        assert sub.count == 2

    def test_slice_to_end(self):
        series = self._make_series(5)
        sub = series.slice(3)
        assert sub.count == 2

    def test_len(self):
        series = self._make_series(4)
        assert len(series) == 4

    def test_iter(self):
        series = self._make_series(3)
        bars = list(series)
        assert len(bars) == 3
        assert all(isinstance(b, OHLCV) for b in bars)

    def test_getitem(self):
        series = self._make_series(5)
        bar = series[2]
        assert bar.open == Decimal("102")

    def test_getitem_slice(self):
        series = self._make_series(5)
        bars = series[1:4]
        assert len(bars) == 3

    def test_empty_series_properties(self):
        series = HistoricalSeries()
        assert series.count == 0
        assert series.start_date is None
        assert series.end_date is None
        assert series.first is None
        assert series.last is None
        assert series.highs == []
        assert series.lows == []
        assert series.closes == []
        assert series.volumes == []
        assert series.price_range == (Decimal("0"), Decimal("0"))
        assert series.total_volume == 0
        assert len(series) == 0
        assert list(series) == []

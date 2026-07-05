"""Contract tests — Scanner contract.

Verifies ScanCriteria (PriceAbove, PriceBelow, VolumeSpike, CrossingMA)
and the Scanner.scan() lifecycle.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from inc_trade.domain.entities import Candle, Quote
from inc_trade.market.scanner.criteria import (
    CrossingMA,
    PriceAbove,
    PriceBelow,
    VolumeSpike,
)
from inc_trade.market.scanner.result import ScanResult
from inc_trade.market.scanner.scanner import Scanner


class _FakeInstrument:
    """Minimal instrument stub for scanning."""

    def __init__(
        self,
        symbol: str,
        exchange: str = "NSE",
    ) -> None:
        self.symbol = symbol
        self.exchange = exchange
        self.composite_key = f"{exchange}:{symbol}"


def _make_fake_registry(
    symbols: dict[str, _FakeInstrument],
) -> Any:
    """Build a minimal registry that returns instruments via get_all()."""
    from inc_trade.market.instrument_registry import InstrumentRegistry

    reg = InstrumentRegistry()
    for key, inst in symbols.items():
        # Inject directly into the private dict for test isolation
        reg._instruments[key] = inst
    return reg


class _FakeMarketData:
    """Stub market data for scanner criteria evaluation."""

    def __init__(self) -> None:
        self._quotes: dict[str, Quote] = {}
        self._candles: dict[str, list[Candle]] = {}
        self._quote_states: dict[str, Any] = {}

    def set_quote(self, symbol: str, exchange: str, ltp: Decimal) -> None:
        key = f"{exchange}:{symbol}"
        self._quotes[key] = Quote(
            symbol=symbol,
            ltp=ltp,
            exchange=exchange,
        )

    def set_candles(
        self,
        symbol: str,
        exchange: str,
        candles: list[Candle],
    ) -> None:
        key = f"{exchange}:{symbol}"
        self._candles[key] = list(candles)

    def set_quote_state(
        self,
        symbol: str,
        exchange: str,
        state: Any,
    ) -> None:
        key = f"{exchange}:{symbol}"
        self._quote_states[key] = state

    def quote(
        self,
        symbol: str,
        exchange: str = "NSE",
    ) -> Quote:
        key = f"{exchange}:{symbol}"
        if key not in self._quotes:
            raise KeyError(f"No quote for {key}")
        return self._quotes[key]

    def ohlcv(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        key = f"{exchange}:{symbol}"
        return [c for c in self._candles.get(key, []) if start_time <= c.timestamp <= end_time]

    def quote_state(
        self,
        symbol: str,
        exchange: str = "NSE",
    ) -> Any:
        key = f"{exchange}:{symbol}"
        return self._quote_states.get(key)


class _QuoteStateStub:
    """Minimal stub for VolumeSpike's quote_state access."""

    def __init__(self, volume: int = 0, open_val: int = 0) -> None:
        self.volume = volume
        self.open = open_val


class ScannerContractTests:
    """Mixin-style contract tests for Scanner and criteria."""

    # ── Criteria: PriceAbove ────────────────────────────────────────────

    def test_price_above_matches_when_ltp_geq_threshold(self, scanner: Scanner) -> None:
        """Ensure scope of 'scanner' includes market_data fixture."""
        del scanner  # not used in this test
        mkt = _FakeMarketData()
        mkt.set_quote("RELIANCE", "NSE", Decimal("2500"))
        inst = _FakeInstrument("RELIANCE")

        criterion = PriceAbove(Decimal("2500"))
        assert criterion.matches(inst, mkt)

    def test_price_above_does_not_match_when_ltp_below_threshold(self, scanner: Scanner) -> None:
        del scanner
        mkt = _FakeMarketData()
        mkt.set_quote("RELIANCE", "NSE", Decimal("2400"))
        inst = _FakeInstrument("RELIANCE")

        criterion = PriceAbove(Decimal("2500"))
        assert not criterion.matches(inst, mkt)

    def test_price_above_describe(self, scanner: Scanner) -> None:
        del scanner
        assert PriceAbove(Decimal("2500")).describe() == "PriceAbove(2500)"

    # ── Criteria: PriceBelow ────────────────────────────────────────────

    def test_price_below_matches_when_ltp_leq_threshold(self, scanner: Scanner) -> None:
        del scanner
        mkt = _FakeMarketData()
        mkt.set_quote("RELIANCE", "NSE", Decimal("2400"))
        inst = _FakeInstrument("RELIANCE")

        criterion = PriceBelow(Decimal("2500"))
        assert criterion.matches(inst, mkt)

    def test_price_below_does_not_match_when_ltp_above_threshold(self, scanner: Scanner) -> None:
        del scanner
        mkt = _FakeMarketData()
        mkt.set_quote("RELIANCE", "NSE", Decimal("2600"))
        inst = _FakeInstrument("RELIANCE")

        criterion = PriceBelow(Decimal("2500"))
        assert not criterion.matches(inst, mkt)

    def test_price_below_describe(self, scanner: Scanner) -> None:
        del scanner
        assert PriceBelow(Decimal("2000")).describe() == "PriceBelow(2000)"

    # ── Criteria: VolumeSpike ───────────────────────────────────────────

    def test_volume_spike_matches_when_volume_exceeds_multiplier(self, scanner: Scanner) -> None:
        del scanner
        mkt = _FakeMarketData()
        mkt.set_quote_state("RELIANCE", "NSE", _QuoteStateStub(volume=1000, open_val=100))
        inst = _FakeInstrument("RELIANCE")

        criterion = VolumeSpike(Decimal("2"))
        # volume (1000) >= 2 * baseline (100) → True
        assert criterion.matches(inst, mkt)

    def test_volume_spike_does_not_match_when_low_volume(self, scanner: Scanner) -> None:
        del scanner
        mkt = _FakeMarketData()
        mkt.set_quote_state("RELIANCE", "NSE", _QuoteStateStub(volume=50, open_val=100))
        inst = _FakeInstrument("RELIANCE")

        criterion = VolumeSpike(Decimal("2"))
        # volume (50) < 2 * baseline (100) → False
        assert not criterion.matches(inst, mkt)

    def test_volume_spike_does_not_match_when_no_state(self, scanner: Scanner) -> None:
        del scanner
        mkt = _FakeMarketData()
        inst = _FakeInstrument("RELIANCE")

        criterion = VolumeSpike(Decimal("2"))
        # No quote_state → return False
        assert not criterion.matches(inst, mkt)

    def test_volume_spike_describe(self, scanner: Scanner) -> None:
        del scanner
        assert VolumeSpike(Decimal("3")).describe() == "VolumeSpike(x3)"

    # ── Criteria: CrossingMA ────────────────────────────────────────────

    def test_crossing_ma_matches_when_ltp_above_sma(self, scanner: Scanner) -> None:
        del scanner
        now = datetime.now(UTC)
        mkt = _FakeMarketData()
        mkt.set_quote("RELIANCE", "NSE", Decimal("200"))
        # 25 candles with close=100, so SMA ~ 100; LTP=200 > 100
        candles = [
            Candle(
                symbol="RELIANCE",
                timestamp=now - timedelta(days=25 - i),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("100"),
                volume=1000,
            )
            for i in range(25)
        ]
        mkt.set_candles("RELIANCE", "NSE", candles)
        inst = _FakeInstrument("RELIANCE")

        criterion = CrossingMA(period=20)
        assert criterion.matches(inst, mkt)

    def test_crossing_ma_does_not_match_when_ltp_below_sma(self, scanner: Scanner) -> None:
        del scanner
        now = datetime.now(UTC)
        mkt = _FakeMarketData()
        mkt.set_quote("RELIANCE", "NSE", Decimal("50"))
        candles = [
            Candle(
                symbol="RELIANCE",
                timestamp=now - timedelta(days=25 - i),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("100"),
                volume=1000,
            )
            for i in range(25)
        ]
        mkt.set_candles("RELIANCE", "NSE", candles)
        inst = _FakeInstrument("RELIANCE")

        criterion = CrossingMA(period=20)
        assert not criterion.matches(inst, mkt)

    def test_crossing_ma_describe(self, scanner: Scanner) -> None:
        del scanner
        assert CrossingMA(period=20).describe() == "CrossingMA(period=20)"

    # ── Scanner.scan() lifecycle ────────────────────────────────────────

    def test_scan_returns_scan_result(self, scanner: Scanner) -> None:
        criterion = PriceAbove(Decimal("0"))
        result = scanner.scan(criterion)
        assert isinstance(result, ScanResult)

    def test_scan_matches_applicable_instruments(self, scanner: Scanner) -> None:
        criterion = PriceAbove(Decimal("2500"))
        result = scanner.scan(criterion)
        # RELIANCE has LTP 3000 >= 2500, TCS has LTP 2000 < 2500
        matched_symbols = result.symbols()
        assert "NSE:RELIANCE" in matched_symbols
        assert "NSE:TCS" not in matched_symbols

    def test_scan_returns_total_scanned(self, scanner: Scanner) -> None:
        criterion = PriceAbove(Decimal("0"))
        result = scanner.scan(criterion)
        assert result.total_scanned == 2

    def test_scan_with_empty_registry_returns_no_matches(self, scanner: Scanner) -> None:
        del scanner
        from inc_trade.market.instrument_registry import InstrumentRegistry

        reg = InstrumentRegistry()
        mkt = _FakeMarketData()
        s = Scanner(registry=reg, market_data=mkt)
        criterion = PriceAbove(Decimal("0"))
        result = s.scan(criterion)
        assert len(result) == 0
        assert result.total_scanned == 0

    def test_scan_filters_by_symbols(self, scanner: Scanner) -> None:
        criterion = PriceAbove(Decimal("0"))
        result = scanner.scan(criterion, symbols=["NSE:RELIANCE"])
        assert result.total_scanned == 1
        assert result.symbols() == ["NSE:RELIANCE"]

    def test_scan_with_callback_invokes_per_match(self, scanner: Scanner) -> None:
        invoked: list[str] = []

        def cb(inst: Any, reason: str) -> None:
            invoked.append(inst.composite_key)

        criterion = PriceAbove(Decimal("2500"))
        scanner.scan_with_callback(criterion, cb)

        assert "NSE:RELIANCE" in invoked
        # TCS should NOT match because LTP=2000 < 2500
        assert "NSE:TCS" not in invoked


@pytest.mark.contract
class TestScannerContractConformance:
    """Base test class — override ``scanner`` fixture for concrete instances."""

    @pytest.fixture
    def scanner(self) -> Scanner:
        mkt = _FakeMarketData()
        mkt.set_quote("RELIANCE", "NSE", Decimal("3000"))
        mkt.set_quote("TCS", "NSE", Decimal("2000"))

        reg = _make_fake_registry(
            {
                "NSE:RELIANCE": _FakeInstrument("RELIANCE"),
                "NSE:TCS": _FakeInstrument("TCS"),
            }
        )

        return Scanner(registry=reg, market_data=mkt)

    def test_price_above_matches_when_ltp_geq_threshold(self, scanner: Scanner) -> None:
        ScannerContractTests().test_price_above_matches_when_ltp_geq_threshold(scanner)

    def test_price_above_does_not_match_when_ltp_below_threshold(self, scanner: Scanner) -> None:
        ScannerContractTests().test_price_above_does_not_match_when_ltp_below_threshold(scanner)

    def test_price_above_describe(self, scanner: Scanner) -> None:
        ScannerContractTests().test_price_above_describe(scanner)

    def test_price_below_matches_when_ltp_leq_threshold(self, scanner: Scanner) -> None:
        ScannerContractTests().test_price_below_matches_when_ltp_leq_threshold(scanner)

    def test_price_below_does_not_match_when_ltp_above_threshold(self, scanner: Scanner) -> None:
        ScannerContractTests().test_price_below_does_not_match_when_ltp_above_threshold(scanner)

    def test_price_below_describe(self, scanner: Scanner) -> None:
        ScannerContractTests().test_price_below_describe(scanner)

    def test_volume_spike_matches_when_volume_exceeds_multiplier(self, scanner: Scanner) -> None:
        ScannerContractTests().test_volume_spike_matches_when_volume_exceeds_multiplier(scanner)

    def test_volume_spike_does_not_match_when_low_volume(self, scanner: Scanner) -> None:
        ScannerContractTests().test_volume_spike_does_not_match_when_low_volume(scanner)

    def test_volume_spike_does_not_match_when_no_state(self, scanner: Scanner) -> None:
        ScannerContractTests().test_volume_spike_does_not_match_when_no_state(scanner)

    def test_volume_spike_describe(self, scanner: Scanner) -> None:
        ScannerContractTests().test_volume_spike_describe(scanner)

    def test_crossing_ma_matches_when_ltp_above_sma(self, scanner: Scanner) -> None:
        ScannerContractTests().test_crossing_ma_matches_when_ltp_above_sma(scanner)

    def test_crossing_ma_does_not_match_when_ltp_below_sma(self, scanner: Scanner) -> None:
        ScannerContractTests().test_crossing_ma_does_not_match_when_ltp_below_sma(scanner)

    def test_crossing_ma_describe(self, scanner: Scanner) -> None:
        ScannerContractTests().test_crossing_ma_describe(scanner)

    def test_scan_returns_scan_result(self, scanner: Scanner) -> None:
        ScannerContractTests().test_scan_returns_scan_result(scanner)

    def test_scan_matches_applicable_instruments(self, scanner: Scanner) -> None:
        ScannerContractTests().test_scan_matches_applicable_instruments(scanner)

    def test_scan_returns_total_scanned(self, scanner: Scanner) -> None:
        ScannerContractTests().test_scan_returns_total_scanned(scanner)

    def test_scan_with_empty_registry_returns_no_matches(self, scanner: Scanner) -> None:
        ScannerContractTests().test_scan_with_empty_registry_returns_no_matches(scanner)

    def test_scan_filters_by_symbols(self, scanner: Scanner) -> None:
        ScannerContractTests().test_scan_filters_by_symbols(scanner)

    def test_scan_with_callback_invokes_per_match(self, scanner: Scanner) -> None:
        ScannerContractTests().test_scan_with_callback_invokes_per_match(scanner)

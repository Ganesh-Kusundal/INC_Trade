"""Unit tests for the Market Scanner package."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from brokers.domain.entities import Quote
from brokers.market.instrument import Instrument
from brokers.market.instrument_registry import InstrumentRegistry
from brokers.market.scanner.criteria import (
    PriceAbove,
    PriceBelow,
    VolumeSpike,
)
from brokers.market.scanner.result import ScanResult
from brokers.market.scanner.scanner import Scanner


def _make_quote(symbol: str, ltp: Decimal, exchange: str = "NSE") -> Quote:
    return Quote(symbol=symbol, exchange=exchange, ltp=ltp, volume=100)


@pytest.fixture
def registry() -> InstrumentRegistry:
    reg = InstrumentRegistry()
    reg.get_or_create("NSE:RELIANCE", lambda: Instrument(symbol="RELIANCE", exchange="NSE"))
    reg.get_or_create("NSE:TCS", lambda: Instrument(symbol="TCS", exchange="NSE"))
    reg.get_or_create("NSE:INFY", lambda: Instrument(symbol="INFY", exchange="NSE"))
    return reg


@pytest.fixture
def market_data() -> Any:
    md = MagicMock()
    md.quote.side_effect = lambda sym, exch="NSE": _make_quote(
        sym,
        {
            "RELIANCE": Decimal("2500"),
            "TCS": Decimal("3000"),
            "INFY": Decimal("1500"),
        }.get(sym, Decimal("1000")),
    )
    md.quote_state.side_effect = lambda sym, exch="NSE": MagicMock(volume=200, open=Decimal("100"))
    md.ohlcv.return_value = []
    return md


class TestPriceAbove:
    def test_matches_when_above_threshold(self, market_data: Any) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        assert PriceAbove(Decimal("2000")).matches(inst, market_data) is True

    def test_does_not_match_when_below(self, market_data: Any) -> None:
        inst = Instrument(symbol="INFY", exchange="NSE")
        assert PriceAbove(Decimal("2000")).matches(inst, market_data) is False

    def test_describe(self) -> None:
        assert PriceAbove(Decimal("100")).describe() == "PriceAbove(100)"


class TestPriceBelow:
    def test_matches_when_below_threshold(self, market_data: Any) -> None:
        inst = Instrument(symbol="INFY", exchange="NSE")
        assert PriceBelow(Decimal("2000")).matches(inst, market_data) is True


class TestVolumeSpike:
    def test_no_match_when_state_unavailable(self) -> None:
        md = MagicMock()
        md.quote_state.side_effect = Exception("nope")
        inst = Instrument(symbol="X", exchange="NSE")
        assert VolumeSpike().matches(inst, md) is False


class TestScanResult:
    def test_len(self) -> None:
        r = ScanResult()
        assert len(r) == 0
        assert not bool(r)
        r.matched.append((Instrument(symbol="X", exchange="NSE"), "reason"))
        assert len(r) == 1
        assert bool(r) is True

    def test_symbols(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        r = ScanResult(matched=[(inst, "PriceAbove(2500)")])
        assert r.symbols() == ["NSE:RELIANCE"]


class TestScanner:
    def test_scan_filters_by_criteria(self, registry: InstrumentRegistry, market_data: Any) -> None:
        scanner = Scanner(registry, market_data)
        result = scanner.scan(PriceAbove(Decimal("2000")))
        assert result.total_scanned == 3
        assert len(result.matched) == 2  # RELIANCE, TCS
        assert {inst.symbol for inst, _ in result.matched} == {"RELIANCE", "TCS"}

    def test_scan_with_symbol_filter(self, registry: InstrumentRegistry, market_data: Any) -> None:
        scanner = Scanner(registry, market_data)
        result = scanner.scan(PriceAbove(Decimal("2000")), symbols=["NSE:RELIANCE"])
        assert result.total_scanned == 1
        assert len(result.matched) == 1

    def test_scan_with_callback(self, registry: InstrumentRegistry, market_data: Any) -> None:
        scanner = Scanner(registry, market_data)
        seen: list[str] = []

        def cb(instrument: Any, reason: str) -> None:
            seen.append(instrument.symbol)

        scanner.scan_with_callback(PriceAbove(Decimal("2000")), cb)
        assert set(seen) == {"RELIANCE", "TCS"}

    def test_scan_records_duration(self, registry: InstrumentRegistry, market_data: Any) -> None:
        scanner = Scanner(registry, market_data)
        result = scanner.scan(PriceAbove(Decimal("0")))
        assert result.duration_ms >= 0


class TestScannerIsolation:
    """Scanner must not import from forbidden layers."""

    def test_scanner_does_not_import_adapters(self) -> None:
        from brokers.market.scanner import scanner as mod

        src = mod.__file__
        assert src is not None
        content = open(src).read()
        for forbidden in (
            "brokers.adapters",
            "brokers.trading",
            "brokers.services",
            "brokers.infrastructure",
        ):
            assert forbidden not in content, f"scanner.py imports {forbidden}"

    def test_criteria_does_not_import_adapters(self) -> None:
        from brokers.market.scanner import criteria as mod

        content = open(mod.__file__).read()
        for forbidden in (
            "brokers.adapters",
            "brokers.trading",
            "brokers.services",
            "brokers.infrastructure",
        ):
            assert forbidden not in content, f"criteria.py imports {forbidden}"

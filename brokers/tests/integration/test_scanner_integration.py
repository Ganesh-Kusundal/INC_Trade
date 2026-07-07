"""Integration tests for Scanner with paper broker MarketDataContext.

Tests PriceAbove, PriceBelow, VolumeSpike, and CrossingMA criteria
against real data through the scanner.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from brokers.market.context import MarketDataContext
from brokers.market.instrument import Instrument
from brokers.market.instrument_registry import InstrumentRegistry
from brokers.market.scanner.criteria import (
    CrossingMA,
    PriceAbove,
    PriceBelow,
    VolumeSpike,
)
from brokers.market.scanner.result import ScanResult
from brokers.market.scanner.scanner import Scanner

from brokers.adapters.paper.gateway import PaperGateway
from brokers.adapters.replay.engine import ReplayEngine

_TODAY = datetime.now(UTC).strftime("%Y-%m-%d")

CSV_CONTENT = f"""symbol,exchange,timestamp,open,high,low,close,volume
RELIANCE,NSE,{_TODAY} 00:15:00,2500.00,2510.00,2495.00,2505.00,500000
RELIANCE,NSE,{_TODAY} 00:20:00,2505.00,2515.00,2500.00,2510.00,600000
RELIANCE,NSE,{_TODAY} 00:25:00,2510.00,2520.00,2505.00,2515.00,550000
TCS,NSE,{_TODAY} 00:15:00,3500.00,3520.00,3490.00,3510.00,300000
TCS,NSE,{_TODAY} 00:30:00,3510.00,3530.00,3505.00,3525.00,450000
INFY,NSE,{_TODAY} 00:15:00,1800.00,1820.00,1795.00,1810.00,200000
"""


@pytest.fixture
def csv_file() -> str:
    """Create a temporary CSV file with sample candle data."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(CSV_CONTENT)
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def registry() -> InstrumentRegistry:
    """InstrumentRegistry with a few known instruments."""
    reg = InstrumentRegistry()
    reg.get_or_create(
        "NSE:RELIANCE",
        lambda: Instrument(
            symbol="RELIANCE",
            exchange="NSE",
            segment="NSE_EQ",
            name="Reliance Industries",
            lot_size=1,
        ),
    )
    reg.get_or_create(
        "NSE:TCS",
        lambda: Instrument(
            symbol="TCS",
            exchange="NSE",
            segment="NSE_EQ",
            name="Tata Consultancy Services",
            lot_size=1,
        ),
    )
    reg.get_or_create(
        "NSE:INFY",
        lambda: Instrument(
            symbol="INFY",
            exchange="NSE",
            segment="NSE_EQ",
            name="Infosys",
            lot_size=1,
        ),
    )
    return reg


@pytest.fixture
def paper_gateway() -> PaperGateway:
    """PaperGateway with preset quotes."""
    gw = PaperGateway()
    gw.set_quote("RELIANCE", Decimal("2600.00"))
    gw.set_quote("TCS", Decimal("3400.00"))
    gw.set_quote("INFY", Decimal("1800.00"))
    return gw


@pytest.fixture
def market_context(
    registry: InstrumentRegistry,
    paper_gateway: PaperGateway,
    csv_file: str,
) -> MarketDataContext:
    """MarketDataContext with paper gateway market data and replay historical."""
    replay = ReplayEngine(speed=0)
    replay.load_csv(csv_file)
    ctx = MarketDataContext(
        registry=registry,
        market_data=paper_gateway.market_data,
        historical=replay,
    )
    return ctx


@pytest.mark.integration
class TestScannerPriceCriteria:
    """Tests for PriceAbove and PriceBelow criteria."""

    def test_price_above_matches(self, registry: InstrumentRegistry, paper_gateway: PaperGateway):
        scanner = Scanner(registry, paper_gateway.market_data)
        result = scanner.scan(PriceAbove(Decimal("2550.00")))
        assert isinstance(result, ScanResult)
        assert result.total_scanned == 3
        # RELIANCE (2600) and TCS (3400) are both above 2550
        matched_symbols = [inst.symbol for inst, _ in result]
        assert "RELIANCE" in matched_symbols
        assert "TCS" in matched_symbols
        assert "INFY" not in matched_symbols  # 1800 is below 2550

    def test_price_above_filters(self, registry: InstrumentRegistry, paper_gateway: PaperGateway):
        scanner = Scanner(registry, paper_gateway.market_data)
        # Only RELIANCE (2600) has LTP above 2500
        result = scanner.scan(PriceAbove(Decimal("2000.00")))
        matched_symbols = [inst.symbol for inst, _ in result]
        assert "RELIANCE" in matched_symbols
        assert "TCS" in matched_symbols
        assert "INFY" not in matched_symbols  # 1800 is below 2000

    def test_price_below_matches(self, registry: InstrumentRegistry, paper_gateway: PaperGateway):
        scanner = Scanner(registry, paper_gateway.market_data)
        result = scanner.scan(PriceBelow(Decimal("2000.00")))
        matched_symbols = [inst.symbol for inst, _ in result]
        assert "INFY" in matched_symbols
        assert "RELIANCE" not in matched_symbols

    def test_price_below_no_match(self, registry: InstrumentRegistry, paper_gateway: PaperGateway):
        scanner = Scanner(registry, paper_gateway.market_data)
        result = scanner.scan(PriceBelow(Decimal("1000.00")))
        assert len(result) == 0

    def test_scan_with_symbol_filter(
        self, registry: InstrumentRegistry, paper_gateway: PaperGateway
    ):
        scanner = Scanner(registry, paper_gateway.market_data)
        result = scanner.scan(
            PriceAbove(Decimal("2000.00")),
            symbols=["NSE:RELIANCE"],
        )
        assert result.total_scanned == 1
        assert len(result) == 1


@pytest.mark.integration
class TestScannerVolumeSpike:
    """Tests for VolumeSpike criterion with QuoteState."""

    def test_volume_spike_match(
        self, registry: InstrumentRegistry, market_context: MarketDataContext
    ):
        """Set up a QuoteState with volume and verify VolumeSpike matches."""
        # Pre-populate quote_state for INFY with non-zero volume
        qs = market_context.quote_state("INFY")
        qs.volume = 500000
        qs.open = Decimal("100")

        scanner = Scanner(registry, market_context)
        result = scanner.scan(VolumeSpike(Decimal("2")))
        # Current volume (500000) is >= 2 * 100 = 200, so it matches
        matched_symbols = [inst.symbol for inst, _ in result]
        assert "INFY" in matched_symbols

    def test_volume_spike_no_match_zero_volume(
        self, registry: InstrumentRegistry, market_context: MarketDataContext
    ):
        """VolumeSpike should not match when quote_state has zero volume."""
        scanner = Scanner(registry, market_context)
        result = scanner.scan(VolumeSpike(Decimal("2")))
        assert len(result) == 0

    def test_volume_spike_no_match_low_open(
        self, registry: InstrumentRegistry, market_context: MarketDataContext
    ):
        """VolumeSpike does not match when open <= 0."""
        qs = market_context.quote_state("RELIANCE")
        qs.volume = 500000
        qs.open = Decimal("0")  # open is 0, so baseline is 0 → no match
        scanner = Scanner(registry, market_context)
        result = scanner.scan(VolumeSpike(Decimal("2")))
        assert len(result) == 0


@pytest.mark.integration
class TestScannerCrossingMA:
    """Tests for CrossingMA criterion with historical data."""

    def test_crossing_ma_matches(
        self, registry: InstrumentRegistry, market_context: MarketDataContext
    ):
        """RELIANCE LTP (2600) > SMA of 3 daily candles ~ 2510."""
        scanner = Scanner(registry, market_context)
        # Short period to work with limited data
        result = scanner.scan(CrossingMA(period=3))
        matched_symbols = [inst.symbol for inst, _ in result]
        # RELIANCE has 3 candles, close prices: 2505, 2510, 2515 → SMA = 2510
        # RELIANCE LTP = 2600 > 2510 → matches
        assert "RELIANCE" in matched_symbols

    def test_crossing_ma_not_enough_candles(
        self, registry: InstrumentRegistry, market_context: MarketDataContext
    ):
        """No match when there aren't enough candles for the period."""
        scanner = Scanner(registry, market_context)
        # Period=100 is more than available candles → no match
        result = scanner.scan(CrossingMA(period=100))
        assert len(result) == 0


@pytest.mark.integration
class TestScannerResult:
    """Tests for ScanResult structure."""

    def test_scan_result_type(self, registry: InstrumentRegistry, paper_gateway: PaperGateway):
        scanner = Scanner(registry, paper_gateway.market_data)
        result = scanner.scan(PriceAbove(Decimal("2500.00")))
        assert isinstance(result, ScanResult)
        assert result.total_scanned > 0
        assert result.duration_ms >= 0
        assert hasattr(result, "timestamp")

    def test_scan_result_iteration(self, registry: InstrumentRegistry, paper_gateway: PaperGateway):
        scanner = Scanner(registry, paper_gateway.market_data)
        result = scanner.scan(PriceAbove(Decimal("2500.00")))
        for instrument, reason in result:
            assert isinstance(reason, str)
            assert hasattr(instrument, "symbol")
            assert hasattr(instrument, "exchange")

    def test_scan_result_bool(self, registry: InstrumentRegistry, paper_gateway: PaperGateway):
        scanner = Scanner(registry, paper_gateway.market_data)
        result = scanner.scan(PriceAbove(Decimal("3000.00")))
        # RELIANCE at 2600, TCS at 3400 → only TCS matches
        assert bool(result) is True

    def test_scan_result_symbols(self, registry: InstrumentRegistry, paper_gateway: PaperGateway):
        scanner = Scanner(registry, paper_gateway.market_data)
        result = scanner.scan(PriceAbove(Decimal("2000.00")))
        symbols = result.symbols()
        assert "NSE:RELIANCE" in symbols
        assert "NSE:TCS" in symbols

    def test_scan_with_callback(self, registry: InstrumentRegistry, paper_gateway: PaperGateway):
        scanner = Scanner(registry, paper_gateway.market_data)
        results: list[str] = []

        def callback(instrument: object, reason: str) -> None:
            results.append(f"{getattr(instrument, 'symbol', '?')}:{reason}")

        result = scanner.scan_with_callback(PriceAbove(Decimal("2500.00")), callback)
        assert len(results) == len(result)
        for entry in results:
            assert "PriceAbove" in entry

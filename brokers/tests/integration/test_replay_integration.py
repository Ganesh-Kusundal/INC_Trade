"""Integration tests for ReplayEngine — uses CSV data loaded in-memory.

Tests the MarketDataPort, HistoricalProvider, and StreamingPort interfaces
of the ReplayEngine with speed=0 (instant replay).
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from inc_trade.domain.entities import Candle, MarketDepth, Quote

from brokers.adapters.replay.engine import ReplayEngine

CSV_CONTENT = """symbol,exchange,timestamp,open,high,low,close,volume
RELIANCE,NSE,2024-01-02 09:15:00,2500.00,2510.00,2495.00,2505.00,500000
RELIANCE,NSE,2024-01-02 09:20:00,2505.00,2515.00,2500.00,2510.00,600000
TCS,NSE,2024-01-02 09:15:00,3500.00,3520.00,3490.00,3510.00,300000
TCS,NSE,2024-01-02 09:30:00,3510.00,3530.00,3505.00,3525.00,450000
INFY,NSE,2024-01-02 09:15:00,1800.00,1820.00,1795.00,1810.00,200000
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
def engine(csv_file: str) -> ReplayEngine:
    """Create a ReplayEngine with speed=0 and load CSV data."""
    eng = ReplayEngine(speed=0)
    eng.load_csv(csv_file)
    return eng


@pytest.mark.integration
class TestReplayEngineMarketDataPort:
    """Tests for MarketDataPort interface (ltp, quote, depth)."""

    def test_ltp(self, engine: ReplayEngine):
        price = engine.ltp("RELIANCE")
        assert isinstance(price, Decimal)
        # Last candle close = 2510.00
        assert price > 0

    def test_ltp_unknown_symbol_raises(self, engine: ReplayEngine):
        with pytest.raises(KeyError):
            engine.ltp("UNKNOWN")

    def test_quote(self, engine: ReplayEngine):
        q = engine.quote("TCS")
        assert isinstance(q, Quote)
        assert q.symbol == "TCS"
        assert q.exchange == "NSE"
        assert q.ltp > 0
        assert q.volume == 450000  # Last candle volume

    def test_quote_unknown_symbol_raises(self, engine: ReplayEngine):
        with pytest.raises(KeyError):
            engine.quote("UNKNOWN")

    def test_depth(self, engine: ReplayEngine):
        d = engine.depth("RELIANCE")
        assert isinstance(d, MarketDepth)
        assert d.symbol == "RELIANCE"
        assert d.exchange == "NSE"
        # Synthetic depth has 5 bid and 5 ask levels
        assert len(d.bids) == 5
        assert len(d.asks) == 5

    def test_ltp_batch(self, engine: ReplayEngine):
        prices = engine.ltp_batch(["RELIANCE", "TCS", "UNKNOWN"])
        assert "RELIANCE" in prices
        assert "TCS" in prices
        assert "UNKNOWN" not in prices
        assert isinstance(prices["RELIANCE"], Decimal)

    def test_quote_batch(self, engine: ReplayEngine):
        quotes = engine.quote_batch(["RELIANCE", "INFY"])
        assert len(quotes) == 2
        assert all(isinstance(q, Quote) for q in quotes.values())


@pytest.mark.integration
class TestReplayEngineHistoricalProvider:
    """Tests for HistoricalProvider interface."""

    def test_get_historical_candles(self, engine: ReplayEngine):
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, tzinfo=UTC)
        candles = engine.get_historical_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=start,
            end_time=end,
            resolution="1",
        )
        assert len(candles) == 2
        assert all(isinstance(c, Candle) for c in candles)
        assert candles[0].symbol == "RELIANCE"
        assert candles[0].open == Decimal("2500.00")

    def test_get_historical_candles_filtered_range(self, engine: ReplayEngine):
        """Only the first candle should be within this narrow range."""
        start = datetime(2024, 1, 2, 9, 14, tzinfo=UTC)
        end = datetime(2024, 1, 2, 9, 16, tzinfo=UTC)
        candles = engine.get_historical_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=start,
            end_time=end,
            resolution="1",
        )
        assert len(candles) == 1

    def test_get_historical_candles_empty(self, engine: ReplayEngine):
        """No candles for an unknown symbol."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 31, tzinfo=UTC)
        candles = engine.get_historical_candles(
            symbol="UNKNOWN",
            exchange="NSE",
            start_time=start,
            end_time=end,
            resolution="1",
        )
        assert candles == []

    def test_provider_id(self, engine: ReplayEngine):
        assert engine.provider_id == "replay"

    def test_is_available(self, engine: ReplayEngine):
        assert engine.is_available is True


@pytest.mark.integration
class TestReplayEngineSymbols:
    """Tests for symbol helpers."""

    def test_symbols(self, engine: ReplayEngine):
        symbols = engine.symbols()
        assert "NSE:RELIANCE" in symbols
        assert "NSE:TCS" in symbols
        assert "NSE:INFY" in symbols
        assert len(symbols) == 3

    def test_has_symbol(self, engine: ReplayEngine):
        assert engine.has_symbol("RELIANCE")
        assert engine.has_symbol("TCS", "NSE")
        assert not engine.has_symbol("UNKNOWN")
        assert not engine.has_symbol("RELIANCE", "BSE")


@pytest.mark.integration
class TestReplayEngineSpeedControl:
    """Tests for speed control."""

    def test_default_speed(self):
        eng = ReplayEngine()
        assert eng.speed == 1.0

    def test_speed_zero(self, engine: ReplayEngine):
        assert engine.speed == 0.0

    def test_set_speed(self, engine: ReplayEngine):
        engine.speed = 2.5
        assert engine.speed == 2.5

    def test_speed_clamped_to_zero(self, engine: ReplayEngine):
        engine.speed = -1.0
        assert engine.speed == 0.0

    def test_instant_replay_via_speed_zero(self):
        """speed=0 means all data loaded, queries return immediately."""
        eng = ReplayEngine(speed=0)
        # No data loaded yet — just verify the engine is operational
        assert eng.speed == 0.0
        assert len(eng.symbols()) == 0

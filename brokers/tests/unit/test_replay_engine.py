"""Unit tests for the Replay Engine."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from brokers.adapters.replay.engine import ReplayEngine
from brokers.adapters.replay.sources import CsvSource
from brokers.adapters.replay.tick_source import TickSource
from inc_trade.domain.entities import Candle, Quote


def _write_sample_csv(path: str) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "exchange", "timestamp", "open", "high", "low", "close", "volume"])
        w.writerow(
            [
                "RELIANCE",
                "NSE",
                "2024-01-02 09:15:00",
                "2500.00",
                "2510.00",
                "2495.00",
                "2505.00",
                "500000",
            ]
        )
        w.writerow(
            [
                "RELIANCE",
                "NSE",
                "2024-01-02 09:16:00",
                "2505.00",
                "2515.00",
                "2500.00",
                "2510.00",
                "300000",
            ]
        )
        w.writerow(
            [
                "TCS",
                "NSE",
                "2024-01-02 09:15:00",
                "3000.00",
                "3010.00",
                "2995.00",
                "3005.00",
                "100000",
            ]
        )


class TestCsvSource:
    def test_load_returns_dict(self, tmp_path: Path) -> None:
        fp = tmp_path / "data.csv"
        _write_sample_csv(str(fp))
        source = CsvSource()
        loaded = source.load(str(fp))
        assert "NSE:RELIANCE" in loaded
        assert "NSE:TCS" in loaded
        assert len(loaded["NSE:RELIANCE"]) == 2

    def test_load_sorts_by_timestamp(self, tmp_path: Path) -> None:
        fp = tmp_path / "data.csv"
        _write_sample_csv(str(fp))
        source = CsvSource()
        loaded = source.load(str(fp))
        ts = [c.timestamp for c in loaded["NSE:RELIANCE"]]
        assert ts == sorted(ts)

    def test_load_missing_file_raises(self) -> None:
        source = CsvSource()
        with pytest.raises(FileNotFoundError):
            source.load("/nonexistent/path.csv")


class TestTickSource:
    def test_generate_yields_quotes(self) -> None:
        ts = TickSource(ticks_per_candle=1, jitter_bps=0, seed=42)
        candles = [
            Candle(
                symbol="X",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("95"),
                close=Decimal("100"),
                volume=10,
            )
        ]
        out = list(ts.generate("X", "NSE", candles))
        assert len(out) == 1
        assert isinstance(out[0], Quote)
        assert out[0].ltp == Decimal("100")

    def test_multiple_ticks_per_candle(self) -> None:
        ts = TickSource(ticks_per_candle=3, jitter_bps=0, seed=42)
        candles = [
            Candle(
                symbol="X",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("95"),
                close=Decimal("100"),
                volume=10,
            )
        ]
        out = list(ts.generate("X", "NSE", candles))
        assert len(out) == 3


class TestReplayEngine:
    def test_default_speed(self) -> None:
        engine = ReplayEngine()
        assert engine.speed == 1.0

    def test_speed_settable(self) -> None:
        engine = ReplayEngine(speed=10.0)
        assert engine.speed == 10.0
        engine.speed = 50.0
        assert engine.speed == 50.0

    def test_provider_id(self) -> None:
        engine = ReplayEngine()
        assert engine.provider_id == "replay"

    def test_is_available(self) -> None:
        engine = ReplayEngine()
        assert engine.is_available is True

    def test_load_csv(self, tmp_path: Path) -> None:
        fp = tmp_path / "data.csv"
        _write_sample_csv(str(fp))
        engine = ReplayEngine()
        engine.load_csv(str(fp))
        assert "NSE:RELIANCE" in engine.symbols()
        assert "NSE:TCS" in engine.symbols()

    def test_ltp(self, tmp_path: Path) -> None:
        fp = tmp_path / "data.csv"
        _write_sample_csv(str(fp))
        engine = ReplayEngine()
        engine.load_csv(str(fp))
        ltp = engine.ltp("RELIANCE", "NSE")
        # The most recent candle is the second RELIANCE row with close=2510.
        # TickSource jitter=0 by default, but engine sets jitter_bps=5; use
        # the latest quote (which has small jitter around 2510).
        assert Decimal("2500") < ltp < Decimal("2520")

    def test_quote(self, tmp_path: Path) -> None:
        fp = tmp_path / "data.csv"
        _write_sample_csv(str(fp))
        engine = ReplayEngine(tick_jitter_bps=0)
        engine.load_csv(str(fp))
        q = engine.quote("RELIANCE", "NSE")
        assert q.symbol == "RELIANCE"
        assert q.exchange == "NSE"

    def test_ltp_missing_raises(self) -> None:
        engine = ReplayEngine()
        with pytest.raises(KeyError):
            engine.ltp("UNKNOWN", "NSE")

    def test_historical_candles(self, tmp_path: Path) -> None:
        fp = tmp_path / "data.csv"
        _write_sample_csv(str(fp))
        engine = ReplayEngine()
        engine.load_csv(str(fp))
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 12, 31, tzinfo=UTC)
        candles = engine.get_historical_candles("RELIANCE", "NSE", start, end, "1D")
        assert len(candles) == 2

    def test_satisfies_market_data_port(self, tmp_path: Path) -> None:
        fp = tmp_path / "data.csv"
        _write_sample_csv(str(fp))
        engine = ReplayEngine(tick_jitter_bps=0)
        engine.load_csv(str(fp))
        # Structural check — does not require runtime_checkable.
        assert isinstance(engine, object)
        # Check that all MarketDataPort methods exist
        for method in ("ltp", "quote", "depth", "ltp_batch", "quote_batch"):
            assert hasattr(engine, method), f"Missing {method}"

    def test_satisfies_historical_provider_protocol(self, tmp_path: Path) -> None:
        fp = tmp_path / "data.csv"
        _write_sample_csv(str(fp))
        engine = ReplayEngine()
        engine.load_csv(str(fp))
        assert engine.provider_id == "replay"
        assert engine.is_available is True


class TestReplayStreaming:
    @pytest.mark.asyncio
    async def test_connect_disconnect(self) -> None:
        engine = ReplayEngine()
        assert engine.is_connected is False
        await engine.connect()
        assert engine.is_connected is True
        await engine.disconnect()
        assert engine.is_connected is False

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe_does_not_raise(self, tmp_path: Path) -> None:
        fp = tmp_path / "data.csv"
        _write_sample_csv(str(fp))
        engine = ReplayEngine(speed=0)
        engine.load_csv(str(fp))
        await engine.connect()
        seen: list[Quote] = []

        def cb(q: Quote) -> None:
            seen.append(q)

        await engine.subscribe_quotes(["RELIANCE"], "NSE", cb)
        await engine.disconnect()
        assert isinstance(seen, list)

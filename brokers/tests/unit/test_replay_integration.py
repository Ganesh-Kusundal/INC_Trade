"""Integration tests — ReplayEngine registered as a HistoricalRouter provider.

The Replay Engine is a pluggable data source. When registered with
``HistoricalRouter``, it should serve historical candles just like a
broker adapter.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from brokers.adapters.replay import ReplayEngine
from inc_trade.domain.entities import Candle
from inc_trade.infrastructure.cache.memory_cache import MemoryCache
from inc_trade.services.historical_router import HistoricalRouter


def _write_csv(path: str) -> None:
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


class TestReplayAsHistoricalProvider:
    def test_satisfies_historical_provider_protocol(self) -> None:
        engine = ReplayEngine()
        assert engine.provider_id == "replay"
        assert engine.is_available is True

    def test_registered_in_historical_router(self, tmp_path: Path) -> None:
        fp = tmp_path / "data.csv"
        _write_csv(str(fp))
        engine = ReplayEngine()
        engine.load_csv(str(fp))

        router = HistoricalRouter(cache=MemoryCache())
        router.add_provider(engine)
        # Now fetch via router
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 12, 31, tzinfo=UTC)
        candles = router.fetch_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=start,
            end_time=end,
            resolution="1D",
        )
        assert len(candles) == 2
        assert all(isinstance(c, Candle) for c in candles)

    def test_cache_first_with_replay_provider(self, tmp_path: Path) -> None:
        fp = tmp_path / "data.csv"
        _write_csv(str(fp))
        engine = ReplayEngine()
        engine.load_csv(str(fp))

        cache = MemoryCache()
        router = HistoricalRouter(cache=cache)
        router.add_provider(engine)

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 12, 31, tzinfo=UTC)

        # First call → cache miss, hits provider
        candles1 = router.fetch_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=start,
            end_time=end,
            resolution="1D",
        )
        assert len(candles1) == 2
        # Second call → cache hit, no provider
        candles2 = router.fetch_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=start,
            end_time=end,
            resolution="1D",
        )
        assert len(candles2) == 2

    def test_replay_as_market_data_provider(self, tmp_path: Path) -> None:
        """ReplayEngine also implements MarketDataPort — test end-to-end."""
        fp = tmp_path / "data.csv"
        _write_csv(str(fp))
        engine = ReplayEngine(tick_jitter_bps=0)
        engine.load_csv(str(fp))

        # Use as a regular market data source
        ltp = engine.ltp("RELIANCE", "NSE")
        assert isinstance(ltp, Decimal)
        # close of last candle = 2510 (no jitter)
        assert ltp == Decimal("2510")

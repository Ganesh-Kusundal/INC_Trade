"""Integration tests for HistoricalRouter with ReplayEngine provider and MemoryCache.

Tests cache-first routing, provider chaining with primary + fallback,
and fetch_candles_batch.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime

import pytest
from brokers.domain.entities import Candle
from brokers.infrastructure.cache.memory_cache import MemoryCache
from brokers.services.historical_router import HistoricalRouter

from brokers.adapters.replay.engine import ReplayEngine

CSV_CONTENT = """symbol,exchange,timestamp,open,high,low,close,volume
RELIANCE,NSE,2024-01-02 09:15:00,2500.00,2510.00,2495.00,2505.00,500000
RELIANCE,NSE,2024-01-02 09:20:00,2505.00,2515.00,2500.00,2510.00,600000
RELIANCE,NSE,2024-01-03 09:15:00,2510.00,2520.00,2505.00,2515.00,550000
TCS,NSE,2024-01-02 09:15:00,3500.00,3520.00,3490.00,3510.00,300000
TCS,NSE,2024-01-02 09:30:00,3510.00,3530.00,3505.00,3525.00,450000
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
def replay_provider(csv_file: str) -> ReplayEngine:
    """ReplayEngine as a HistoricalProvider with speed=0."""
    eng = ReplayEngine(speed=0)
    eng.load_csv(csv_file)
    return eng


@pytest.fixture
def cache() -> MemoryCache:
    """Empty in-memory cache."""
    return MemoryCache()


@pytest.fixture
def router(cache: MemoryCache, replay_provider: ReplayEngine) -> HistoricalRouter:
    """HistoricalRouter with MemoryCache and ReplayEngine provider."""
    r = HistoricalRouter(cache=cache, providers=[replay_provider])
    return r


def _ts(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


@pytest.mark.integration
class TestHistoricalRouterFetchCandles:
    """Tests for fetch_candles with cache-first routing."""

    def test_fetch_all_candles(self, router: HistoricalRouter):
        candles = router.fetch_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=_ts(2024, 1, 1),
            end_time=_ts(2024, 1, 31),
            resolution="1",
        )
        assert len(candles) == 3
        assert all(isinstance(c, Candle) for c in candles)
        assert candles[0].symbol == "RELIANCE"

    def test_fetch_candles_filtered_range(self, router: HistoricalRouter):
        """Only one candle falls within this narrow time window."""
        candles = router.fetch_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=_ts(2024, 1, 2, 9, 14),
            end_time=_ts(2024, 1, 2, 9, 21),
            resolution="1",
        )
        assert len(candles) == 2

    def test_fetch_candles_empty_for_unknown_symbol(self, router: HistoricalRouter):
        candles = router.fetch_candles(
            symbol="UNKNOWN",
            exchange="NSE",
            start_time=_ts(2024, 1, 1),
            end_time=_ts(2024, 1, 31),
            resolution="1",
        )
        assert candles == []

    def test_fetch_candles_no_providers_returns_empty(self, cache: MemoryCache):
        """Router with no providers returns no candles."""
        r = HistoricalRouter(cache=cache)
        candles = r.fetch_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=_ts(2024, 1, 1),
            end_time=_ts(2024, 1, 31),
            resolution="1",
        )
        assert candles == []

    def test_candles_sorted_by_timestamp(self, router: HistoricalRouter):
        candles = router.fetch_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=_ts(2024, 1, 1),
            end_time=_ts(2024, 1, 31),
            resolution="1",
        )
        timestamps = [c.timestamp for c in candles]
        assert timestamps == sorted(timestamps)


@pytest.mark.integration
class TestHistoricalRouterCacheFirst:
    """Tests for cache-first routing behavior."""

    def test_cache_populated_after_first_fetch(self, router: HistoricalRouter, cache: MemoryCache):
        router.fetch_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=_ts(2024, 1, 1),
            end_time=_ts(2024, 1, 31),
            resolution="1",
        )
        cache_key = "historical:NSE:RELIANCE:1"
        cached = cache.get(cache_key)
        assert cached is not None
        assert len(cached) == 3

    def test_cache_hit_returns_same_data(self, router: HistoricalRouter, cache: MemoryCache):
        first = router.fetch_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=_ts(2024, 1, 1),
            end_time=_ts(2024, 1, 31),
            resolution="1",
        )
        second = router.fetch_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=_ts(2024, 1, 1),
            end_time=_ts(2024, 1, 31),
            resolution="1",
        )
        assert len(first) == len(second)
        assert first == second

    def test_different_resolutions_have_separate_cache(self, router: HistoricalRouter):
        router.fetch_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=_ts(2024, 1, 1),
            end_time=_ts(2024, 1, 31),
            resolution="1",
        )
        # Different resolution — should still query (cache miss expected)
        candles_15 = router.fetch_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=_ts(2024, 1, 1),
            end_time=_ts(2024, 1, 31),
            resolution="15",
        )
        assert len(candles_15) == 3  # Same data from provider


@pytest.mark.integration
class TestHistoricalRouterProviderChain:
    """Tests for provider chain with primary + fallback."""

    def test_provider_registration(self, router: HistoricalRouter):
        assert router.available_providers == ["replay"]

    def test_add_provider(self, router: HistoricalRouter):
        eng2 = ReplayEngine(speed=0)
        router.add_provider(eng2)
        assert len(router.available_providers) == 2
        assert router.available_providers == ["replay", "replay"]

    def test_remove_provider(self, router: HistoricalRouter):
        assert router.remove_provider("replay") is True
        assert router.available_providers == []
        assert router.remove_provider("nonexistent") is False

    def test_fallback_provider_used_when_primary_fails(self, cache: MemoryCache, csv_file: str):
        """When the first provider has no data, the second is tried."""
        primary = ReplayEngine(speed=0)  # No data loaded
        secondary = ReplayEngine(speed=0)
        secondary.load_csv(csv_file)
        r = HistoricalRouter(cache=cache, providers=[primary, secondary])
        candles = r.fetch_candles(
            symbol="RELIANCE",
            exchange="NSE",
            start_time=_ts(2024, 1, 1),
            end_time=_ts(2024, 1, 31),
            resolution="1",
        )
        assert len(candles) == 3


@pytest.mark.integration
class TestHistoricalRouterBatch:
    """Tests for fetch_candles_batch."""

    def test_fetch_candles_batch(self, router: HistoricalRouter):
        requests = [
            ("RELIANCE", "NSE", _ts(2024, 1, 1), _ts(2024, 1, 31), "1"),
            ("TCS", "NSE", _ts(2024, 1, 1), _ts(2024, 1, 31), "1"),
        ]
        results = router.fetch_candles_batch(requests)
        assert len(results) == 2
        assert len(results[0]) == 3  # 3 RELIANCE candles
        assert len(results[1]) == 2  # 2 TCS candles

    def test_fetch_candles_batch_empty(self, router: HistoricalRouter):
        results = router.fetch_candles_batch([])
        assert results == []

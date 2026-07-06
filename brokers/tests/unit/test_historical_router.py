"""Tests for HistoricalRouter — cache-first, multi-provider data routing."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from inc_trade.domain.cache_policy import (
    CachePolicy,
    policy_for_resolution,
)
from inc_trade.domain.entities import Candle
from inc_trade.infrastructure.cache.memory_cache import MemoryCache
from inc_trade.services.historical_router import HistoricalRouter


def _make_candle(
    symbol: str,
    timestamp: datetime,
    open_p: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: int = 1000,
) -> Candle:
    """Helper to create a test candle."""
    from decimal import Decimal

    return Candle(
        symbol=symbol,
        timestamp=timestamp,
        open=Decimal(str(open_p)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=volume,
    )


class _FakeProvider:
    """Test provider with controllable data and availability."""

    def __init__(
        self,
        provider_id: str,
        candles: list[Candle] | None = None,
        available: bool = True,
    ):
        self._provider_id = provider_id
        self._candles = candles or []
        self._available = available
        self.call_count = 0

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def is_available(self) -> bool:
        return self._available

    def get_historical_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        self.call_count += 1
        return [
            c for c in self._candles if c.symbol == symbol and start_time <= c.timestamp <= end_time
        ]


class _FakeFailingProvider:
    """Provider that raises exceptions to test fallback."""

    def __init__(self, provider_id: str = "failing"):
        self._provider_id = provider_id
        self.call_count = 0

    @property
    def provider_id(self) -> str:
        return self._provider_id

    @property
    def is_available(self) -> bool:
        return True

    def get_historical_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        self.call_count += 1
        msg = f"Provider {self._provider_id} failed"
        raise RuntimeError(msg)


class TestHistoricalRouterBasic:
    """Basic routing behavior."""

    def setup_method(self) -> None:
        self.cache = MemoryCache()
        self.router = HistoricalRouter(cache=self.cache)
        self.t0 = datetime(2024, 1, 1, tzinfo=UTC)
        self.t1 = datetime(2024, 1, 2, tzinfo=UTC)
        self.candles = [
            _make_candle("RELIANCE", self.t0),
            _make_candle("RELIANCE", self.t1),
        ]

    def test_empty_router_returns_empty(self) -> None:
        """No providers → empty result."""
        result = self.router.fetch_candles("RELIANCE", "NSE", self.t0, self.t1, "1D")
        assert result == []

    def test_cache_hit_returns_cached(self) -> None:
        """Cache hit skips provider."""
        provider = _FakeProvider("test", self.candles)
        self.router.add_provider(provider)
        # First call — cache miss, fetches from provider
        result1 = self.router.fetch_candles("RELIANCE", "NSE", self.t0, self.t1, "1D")
        assert len(result1) == 2
        assert provider.call_count == 1
        # Second call — cache hit
        result2 = self.router.fetch_candles("RELIANCE", "NSE", self.t0, self.t1, "1D")
        assert len(result2) == 2
        assert provider.call_count == 1  # Not called again

    def test_cache_miss_fetches_from_provider(self) -> None:
        """Cache miss → router calls provider and populates cache."""
        provider = _FakeProvider("test", self.candles)
        self.router.add_provider(provider)
        result = self.router.fetch_candles("RELIANCE", "NSE", self.t0, self.t1, "1D")
        assert len(result) == 2
        assert provider.call_count == 1


class TestHistoricalRouterProviderFallback:
    """Provider fallback behavior when primary fails."""

    def setup_method(self) -> None:
        self.cache = MemoryCache()
        self.router = HistoricalRouter(cache=self.cache)
        self.t0 = datetime(2024, 1, 1, tzinfo=UTC)
        self.t1 = datetime(2024, 1, 2, tzinfo=UTC)

    def test_fallback_to_secondary(self) -> None:
        """Primary fails → secondary provider serves data."""
        candles = [_make_candle("RELIANCE", self.t0)]
        primary = _FakeFailingProvider("primary")
        secondary = _FakeProvider("secondary", candles)
        self.router.add_provider(primary)
        self.router.add_provider(secondary)
        result = self.router.fetch_candles("RELIANCE", "NSE", self.t0, self.t1, "1D")
        assert len(result) == 1
        assert primary.call_count >= 1
        assert secondary.call_count == 1

    def test_all_providers_fail_returns_empty(self) -> None:
        """All providers fail → empty list."""
        self.router.add_provider(_FakeFailingProvider("p1"))
        self.router.add_provider(_FakeFailingProvider("p2"))
        result = self.router.fetch_candles("RELIANCE", "NSE", self.t0, self.t1, "1D")
        assert result == []

    def test_skips_unavailable_providers(self) -> None:
        """Unavailable providers are skipped."""
        candles = [_make_candle("RELIANCE", self.t0)]
        unavailable = _FakeProvider("unavailable", candles, available=False)
        available = _FakeProvider("available", candles)
        self.router.add_provider(unavailable)
        self.router.add_provider(available)
        result = self.router.fetch_candles("RELIANCE", "NSE", self.t0, self.t1, "1D")
        assert len(result) == 1
        assert unavailable.call_count == 0
        assert available.call_count == 1

    def test_cache_serves_after_provider_failure(self) -> None:
        """After successful fetch, cache serves subsequent requests."""
        candles = [_make_candle("RELIANCE", self.t0)]
        provider = _FakeProvider("test", candles)
        self.router.add_provider(provider)
        # First call — cache miss, fetches from provider
        result1 = self.router.fetch_candles("RELIANCE", "NSE", self.t0, self.t1, "1D")
        assert len(result1) == 1
        assert provider.call_count == 1
        # Remove provider (simulating failure) — cache should serve
        self.router.remove_provider("test")
        result2 = self.router.fetch_candles("RELIANCE", "NSE", self.t0, self.t1, "1D")
        assert len(result2) == 1  # Served from cache


class TestHistoricalRouterCacheKey:
    """Cache key generation and isolation."""

    def setup_method(self) -> None:
        self.cache = MemoryCache()
        self.router = HistoricalRouter(cache=self.cache)
        self.t0 = datetime(2024, 1, 1, tzinfo=UTC)

    def test_different_symbols_different_cache(self) -> None:
        """Different symbols don't share cache entries."""
        c1 = [_make_candle("RELIANCE", self.t0)]
        c2 = [_make_candle("TCS", self.t0)]
        p1 = _FakeProvider("p1", c1)
        p2 = _FakeProvider("p2", c2)
        self.router.add_provider(p1)
        self.router.add_provider(p2)
        r1 = self.router.fetch_candles("RELIANCE", "NSE", self.t0, self.t0, "1D")
        r2 = self.router.fetch_candles("TCS", "NSE", self.t0, self.t0, "1D")
        assert r1[0].symbol == "RELIANCE"
        assert r2[0].symbol == "TCS"

    def test_different_resolutions_different_cache(self) -> None:
        """Different resolutions don't share cache entries."""
        t0 = self.t0
        t1 = t0 + timedelta(hours=1)
        c_1m = [_make_candle("RELIANCE", t0)]
        c_1d = [_make_candle("RELIANCE", t0)]
        p = _FakeProvider("p", c_1m + c_1d)
        self.router.add_provider(p)
        r1 = self.router.fetch_candles("RELIANCE", "NSE", t0, t1, "1")
        assert len(r1) == 1
        r2 = self.router.fetch_candles("RELIANCE", "NSE", t0, t1, "1D")
        assert len(r2) == 1
        assert p.call_count == 2  # Different caches


class TestHistoricalRouterProviderManagement:
    """Provider registration and removal."""

    def setup_method(self) -> None:
        self.cache = MemoryCache()
        self.router = HistoricalRouter(cache=self.cache)

    def test_add_provider(self) -> None:
        p = _FakeProvider("test")
        self.router.add_provider(p)
        assert "test" in self.router.available_providers

    def test_remove_provider(self) -> None:
        p = _FakeProvider("test")
        self.router.add_provider(p)
        assert self.router.remove_provider("test") is True
        assert "test" not in self.router.available_providers

    def test_remove_nonexistent_provider(self) -> None:
        assert self.router.remove_provider("nonexistent") is False

    def test_available_providers_empty_initially(self) -> None:
        assert self.router.available_providers == []


class TestHistoricalRouterBatch:
    """Batch fetch support."""

    def setup_method(self) -> None:
        self.cache = MemoryCache()
        self.router = HistoricalRouter(cache=self.cache)
        self.t0 = datetime(2024, 1, 1, tzinfo=UTC)
        self.t1 = datetime(2024, 1, 2, tzinfo=UTC)
        candles = [_make_candle("RELIANCE", self.t0)]
        self.router.add_provider(_FakeProvider("test", candles))

    def test_batch_fetch(self) -> None:
        requests = [
            ("RELIANCE", "NSE", self.t0, self.t1, "1D"),
            ("TCS", "NSE", self.t0, self.t1, "1D"),
        ]
        results = self.router.fetch_candles_batch(requests)
        assert len(results) == 2


class TestCachePolicy:
    """Cache policy for historical data."""

    def test_policy_for_resolution_intraday(self) -> None:
        policy = policy_for_resolution("1")
        assert isinstance(policy, CachePolicy)
        assert policy.ttl_seconds <= 3600  # Intraday TTLs are short

    def test_policy_for_resolution_daily(self) -> None:
        policy = policy_for_resolution("1D")
        assert policy.ttl_seconds >= 3600  # Daily TTLs are longer

    def test_policy_has_stale_window(self) -> None:
        policy = policy_for_resolution("1")
        assert policy.stale_seconds >= 0


class TestHistoricalRouterMerge:
    """Candle merging and deduplication."""

    def test_merge_deduplicates_by_timestamp(self) -> None:
        t = datetime(2024, 1, 1, tzinfo=UTC)
        existing = [_make_candle("R", t, close=100.0)]
        new_candles = [_make_candle("R", t, close=200.0)]  # Same timestamp
        merged = HistoricalRouter._merge_candles(existing, new_candles)
        assert len(merged) == 1
        assert merged[0].close == 200  # New overwrites

    def test_merge_combines_different_timestamps(self) -> None:
        t1 = datetime(2024, 1, 1, tzinfo=UTC)
        t2 = datetime(2024, 1, 2, tzinfo=UTC)
        existing = [_make_candle("R", t1)]
        new_candles = [_make_candle("R", t2)]
        merged = HistoricalRouter._merge_candles(existing, new_candles)
        assert len(merged) == 2

    def test_merge_sorts_by_timestamp(self) -> None:
        t1 = datetime(2024, 1, 2, tzinfo=UTC)
        t2 = datetime(2024, 1, 1, tzinfo=UTC)
        existing = [_make_candle("R", t1)]
        new_candles = [_make_candle("R", t2)]
        merged = HistoricalRouter._merge_candles(existing, new_candles)
        assert merged[0].timestamp == t2  # Earlier first
        assert merged[1].timestamp == t1

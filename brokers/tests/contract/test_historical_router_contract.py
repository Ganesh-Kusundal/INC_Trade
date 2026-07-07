"""Contract tests — HistoricalRouter contract.

Verifies cache-first routing, provider fallback chain,
pagination, merge/covers-range logic, and batch fetching.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from brokers.domain.cache_policy import CachePolicy
from brokers.domain.entities import Candle


class _DictCache:
    """In-memory cache implementing CachePort."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        return self._data.get(key)

    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        self._data[key] = value

    def delete(self, key: str) -> bool:
        return self._data.pop(key, None) is not None

    def clear(self) -> None:
        self._data.clear()

    def get_stale(self, key: str, max_age_seconds: float) -> tuple[Any, bool]:
        return self._data.get(key), False

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        return {k: self._data[k] for k in keys if k in self._data}

    def set_many(self, items: dict[str, Any], ttl_seconds: float | None = None) -> None:
        self._data.update(items)


class _MockHistoricalProvider:
    """Simple HistoricalProvider that returns fixed candles."""

    def __init__(
        self,
        provider_id: str = "mock",
        available: bool = True,
        candles: list[Candle] | None = None,
    ) -> None:
        self._provider_id = provider_id
        self._available = available
        self._candles = list(candles or [])
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
        return list(self._candles)


class _RaisingProvider:
    """Provider that raises on every call."""

    def __init__(self, provider_id: str = "broken") -> None:
        self._provider_id = provider_id

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
        msg = f"{self._provider_id} is broken"
        raise RuntimeError(msg)


def _make_candle(
    ts: datetime,
    open_val: Decimal = Decimal("100"),
    high: Decimal = Decimal("110"),
    low: Decimal = Decimal("90"),
    close: Decimal = Decimal("105"),
    volume: int = 1000,
) -> Candle:
    return Candle(
        symbol="RELIANCE",
        timestamp=ts,
        open=open_val,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


class HistoricalRouterContractTests:
    """Mixin-style contract tests for HistoricalRouter."""

    def test_cache_first_returns_cached_candles(self, router: Any) -> None:
        """When cache has data covering the range, providers are not called."""
        # We access internal state via the fixture's cache/provider references
        cache: _DictCache = router._cache
        provider: _MockHistoricalProvider = router._providers[0]

        now = datetime.now(UTC)
        candle = _make_candle(now)
        cache.set(router._cache_key("RELIANCE", "NSE", "1D"), [candle])
        before = provider.call_count

        # Single candle at now covers a tight range within the 1-minute tolerance
        result = router.fetch_candles(
            "RELIANCE",
            "NSE",
            now - timedelta(seconds=30),
            now + timedelta(seconds=30),
            "1D",
        )

        assert len(result) >= 1
        assert provider.call_count == before

    def test_cache_miss_delegates_to_provider(self, router: Any) -> None:
        """No cache → provider should be called."""
        now = datetime.now(UTC)
        provider: _MockHistoricalProvider = router._providers[0]
        candle = _make_candle(now)
        provider._candles = [candle]

        result = router.fetch_candles(
            "RELIANCE",
            "NSE",
            now - timedelta(hours=1),
            now + timedelta(hours=1),
            "1D",
        )

        assert len(result) >= 1
        assert provider.call_count == 1

    def test_primary_failure_falls_back(self, router: Any) -> None:
        """When primary provider fails, fallback is used."""
        now = datetime.now(UTC)
        candle = _make_candle(now)
        # Manually replace providers: broken primary, working fallback
        fallback = _MockHistoricalProvider(
            provider_id="fallback",
            candles=[candle],
        )
        router._providers = [_RaisingProvider("broken"), fallback]

        result = router.fetch_candles(
            "RELIANCE",
            "NSE",
            now - timedelta(hours=1),
            now + timedelta(hours=1),
            "1D",
        )

        assert len(result) >= 1
        assert fallback.call_count == 1

    def test_fallback_unavailable_skips(self, router: Any) -> None:
        """Unavailable fallback is skipped; only available providers are tried."""
        now = datetime.now(UTC)
        candle = _make_candle(now)
        available = _MockHistoricalProvider(
            provider_id="good",
            candles=[candle],
        )
        unavailable = _MockHistoricalProvider(
            provider_id="unavail",
            available=False,
            candles=[candle],
        )
        router._providers = [unavailable, available]

        result = router.fetch_candles(
            "RELIANCE",
            "NSE",
            now - timedelta(hours=1),
            now + timedelta(hours=1),
            "1D",
        )

        assert len(result) >= 1
        assert unavailable.call_count == 0
        assert available.call_count == 1

    def test_merge_candles_dedup_by_timestamp(self, router: Any) -> None:
        """Candles with the same timestamp are deduped; new wins."""
        now = datetime.now(UTC)
        old = _make_candle(now, close=Decimal("100"))
        new = _make_candle(now, close=Decimal("200"))

        merged = router._merge_candles([old], [new])

        assert len(merged) == 1
        assert merged[0].close == Decimal("200")

    def test_merge_candles_combines_different_timestamps(self, router: Any) -> None:
        t1 = datetime(2024, 1, 1, tzinfo=UTC)
        t2 = datetime(2024, 1, 2, tzinfo=UTC)
        c1 = _make_candle(t1)
        c2 = _make_candle(t2)

        merged = router._merge_candles([c1], [c2])

        assert len(merged) == 2

    def test_covers_range_true_when_covered(self, router: Any) -> None:
        now = datetime.now(UTC)
        # First candle at range start, last at range end → covered
        candles = [
            _make_candle(now - timedelta(hours=2)),
            _make_candle(now),
        ]
        assert router._covers_range(candles, now - timedelta(hours=2), now)

    def test_covers_range_false_when_empty(self, router: Any) -> None:
        assert not router._covers_range([], datetime.now(UTC), datetime.now(UTC))

    def test_covers_range_false_when_not_covering(self, router: Any) -> None:
        now = datetime.now(UTC)
        candles = [_make_candle(now)]
        assert not router._covers_range(
            candles,
            now - timedelta(days=10),
            now - timedelta(days=5),
        )

    def test_fetch_candles_batch(self, router: Any) -> None:
        """Batch method returns results for each request."""
        now = datetime.now(UTC)
        candle = _make_candle(now)
        provider: _MockHistoricalProvider = router._providers[0]
        provider._candles = [candle]

        requests = [
            ("RELIANCE", "NSE", now - timedelta(hours=1), now, "1D"),
            ("TCS", "NSE", now - timedelta(hours=1), now, "1D"),
        ]
        results = router.fetch_candles_batch(requests)

        assert len(results) == 2
        assert isinstance(results[0], list)
        assert isinstance(results[1], list)

    def test_provider_management_add_remove(self, router: Any) -> None:
        provider = _MockHistoricalProvider("custom")
        router.add_provider(provider)
        assert "custom" in router.available_providers

        router.remove_provider("custom")
        assert "custom" not in router.available_providers

    def test_cache_key_format(self, router: Any) -> None:
        key = router._cache_key("RELIANCE", "NSE", "1D")
        assert key == "historical:NSE:RELIANCE:1D"

    def test_populate_cache_stores_candles(self, router: Any) -> None:
        cache: _DictCache = router._cache
        now = datetime.now(UTC)
        candle = _make_candle(now)

        router._populate_cache(
            "historical:NSE:RELIANCE:1D",
            [candle],
            "1D",
        )

        cached = cache.get("historical:NSE:RELIANCE:1D")
        assert cached is not None
        assert len(cached) == 1

    def test_pagination_split_large_ranges(self, router: Any) -> None:
        """_needs_pagination returns True for ranges > 90 days."""
        now = datetime.now(UTC)
        assert router._needs_pagination(now - timedelta(days=100), now)
        assert not router._needs_pagination(now - timedelta(days=30), now)


@pytest.mark.contract
class TestHistoricalRouterContractConformance:
    """Base test class — override ``router`` fixture."""

    @pytest.fixture
    def router(self) -> Any:
        from brokers.services.historical_router import HistoricalRouter

        cache = _DictCache()
        provider = _MockHistoricalProvider("primary")
        return HistoricalRouter(
            cache=cache,
            providers=[provider],
            default_policy=CachePolicy(ttl_seconds=3600),
        )

    def test_cache_first_returns_cached_candles(self, router: Any) -> None:
        HistoricalRouterContractTests().test_cache_first_returns_cached_candles(router)

    def test_cache_miss_delegates_to_provider(self, router: Any) -> None:
        HistoricalRouterContractTests().test_cache_miss_delegates_to_provider(router)

    def test_primary_failure_falls_back(self, router: Any) -> None:
        HistoricalRouterContractTests().test_primary_failure_falls_back(router)

    def test_fallback_unavailable_skips(self, router: Any) -> None:
        HistoricalRouterContractTests().test_fallback_unavailable_skips(router)

    def test_merge_candles_dedup_by_timestamp(self, router: Any) -> None:
        HistoricalRouterContractTests().test_merge_candles_dedup_by_timestamp(router)

    def test_merge_candles_combines_different_timestamps(self, router: Any) -> None:
        HistoricalRouterContractTests().test_merge_candles_combines_different_timestamps(router)

    def test_covers_range_true_when_covered(self, router: Any) -> None:
        HistoricalRouterContractTests().test_covers_range_true_when_covered(router)

    def test_covers_range_false_when_empty(self, router: Any) -> None:
        HistoricalRouterContractTests().test_covers_range_false_when_empty(router)

    def test_covers_range_false_when_not_covering(self, router: Any) -> None:
        HistoricalRouterContractTests().test_covers_range_false_when_not_covering(router)

    def test_fetch_candles_batch(self, router: Any) -> None:
        HistoricalRouterContractTests().test_fetch_candles_batch(router)

    def test_provider_management_add_remove(self, router: Any) -> None:
        HistoricalRouterContractTests().test_provider_management_add_remove(router)

    def test_cache_key_format(self, router: Any) -> None:
        HistoricalRouterContractTests().test_cache_key_format(router)

    def test_populate_cache_stores_candles(self, router: Any) -> None:
        HistoricalRouterContractTests().test_populate_cache_stores_candles(router)

    def test_pagination_split_large_ranges(self, router: Any) -> None:
        HistoricalRouterContractTests().test_pagination_split_large_ranges(router)

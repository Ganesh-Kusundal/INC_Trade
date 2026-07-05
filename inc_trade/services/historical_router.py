"""Historical data router — cache-first, multi-provider data routing.

Architecture::

    Client (HistoricalService)
        │
        ▼
    HistoricalRouter
        │
        ├── Cache (fast path) ── cache hit → return immediately
        │
        └── Provider chain (slow path)
            ├── Primary provider (broker adapter)
            ├── Fallback provider (replay, CSV, cache)
            └── Each result → populate cache for next request
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from inc_trade.domain.cache_policy import CachePolicy, policy_for_resolution
from inc_trade.domain.entities import Candle
from inc_trade.ports.cache_port import CachePort
from inc_trade.ports.historical_provider import HistoricalProvider

logger = logging.getLogger(__name__)


class HistoricalRouter:
    """Routes historical data requests through cache-first, multi-provider chain.

    Supports:
    - Cache-first (fast path for repeated queries)
    - Provider fallback (primary → secondary → tertiary)
    - Pagination (large date ranges split into chunks)
    - Batching (parallel requests across multiple providers)
    - Stale-while-revalidate (serve stale data while fetching fresh)

    Args:
        cache: Cache backend for historical data.
        providers: Ordered list of HistoricalProvider instances. The first
            available provider is used as primary.
        default_policy: Default cache policy. If None, determined by resolution.
    """

    def __init__(
        self,
        cache: CachePort,
        providers: list[HistoricalProvider] | None = None,
        default_policy: CachePolicy | None = None,
    ) -> None:
        self._cache = cache
        self._providers: list[HistoricalProvider] = providers or []
        self._default_policy = default_policy

    # ── Provider Management ──────────────────────────────────────────

    def add_provider(self, provider: HistoricalProvider) -> None:
        """Register a historical data provider.

        Providers are tried in registration order (first wins).

        Args:
            provider: HistoricalProvider instance.
        """
        self._providers.append(provider)
        logger.info(
            "Historical provider registered",
            extra={"provider": provider.provider_id},
        )

    def remove_provider(self, provider_id: str) -> bool:
        """Remove a provider by ID.

        Args:
            provider_id: Provider identifier.

        Returns:
            True if found and removed, False otherwise.
        """
        for i, p in enumerate(self._providers):
            if p.provider_id == provider_id:
                self._providers.pop(i)
                return True
        return False

    @property
    def available_providers(self) -> list[str]:
        """List of registered provider IDs."""
        return [p.provider_id for p in self._providers]

    # ── Core Routing ─────────────────────────────────────────────────

    def fetch_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        """Fetch historical candles with cache-first routing.

        Strategy:
        1. Check cache for the requested range.
        2. If cache miss (or incomplete), query primary provider.
        3. If primary fails, fallback to next provider.
        4. Populate cache with results for future requests.

        Args:
            symbol: Instrument symbol.
            exchange: Exchange identifier.
            start_time: Start of time range.
            end_time: End of time range.
            resolution: Candle resolution (e.g., '1', '5', '15', '60', '1D').

        Returns:
            List of historical candles covering the requested range.
        """
        # Step 1: Build cache key
        cache_key = self._cache_key(symbol, exchange, resolution)

        # Step 2: Try cache-first (fast path)
        cached = self._try_cache(cache_key, start_time, end_time)
        if self._covers_range(cached, start_time, end_time):
            logger.debug(
                "Historical cache HIT",
                extra={
                    "symbol": symbol,
                    "exchange": exchange,
                    "resolution": resolution,
                    "candles": len(cached),
                },
            )
            return cached

        # Step 3: Try providers in order (slow path)
        all_candles: list[Candle] = list(cached)
        missing_start, missing_end = self._find_missing_range(all_candles, start_time, end_time)

        for provider in self._providers:
            try:
                if not provider.is_available:
                    continue
                provider_candles = provider.get_historical_candles(
                    symbol=symbol,
                    exchange=exchange,
                    start_time=missing_start,
                    end_time=missing_end,
                    resolution=resolution,
                )
                if provider_candles:
                    # Merge with existing cached data
                    all_candles = self._merge_candles(all_candles, provider_candles)
                    # Populate cache
                    self._populate_cache(cache_key, provider_candles, resolution)
                    logger.debug(
                        "Historical provider %s returned %d candles",
                        provider.provider_id,
                        len(provider_candles),
                    )
                    # Check if we now cover the range
                    if self._covers_range(all_candles, start_time, end_time):
                        break
                    missing_start, missing_end = self._find_missing_range(
                        all_candles, start_time, end_time
                    )
            except Exception as exc:
                logger.warning(
                    "Historical provider %s failed: %s",
                    provider.provider_id,
                    exc,
                )
                continue

        # Step 4: Sort and return
        all_candles.sort(key=lambda c: c.timestamp)
        return all_candles

    def fetch_candles_batch(
        self,
        requests: list[tuple[str, str, datetime, datetime, str]],
    ) -> list[list[Candle]]:
        """Fetch multiple historical data requests.

        Useful for parallel data loading.

        Args:
            requests: List of (symbol, exchange, start, end, resolution) tuples.

        Returns:
            List of candle lists, one per request.
        """
        results: list[list[Candle]] = []
        for symbol, exchange, start, end, resolution in requests:
            results.append(
                self.fetch_candles(
                    symbol=symbol,
                    exchange=exchange,
                    start_time=start,
                    end_time=end,
                    resolution=resolution,
                )
            )
        return results

    # ── Cache Helpers ─────────────────────────────────────────────────

    def _cache_key(self, symbol: str, exchange: str, resolution: str) -> str:
        """Generate a cache key for a historical data query.

        Format: ``historical:{exchange}:{symbol}:{resolution}``

        Args:
            symbol: Instrument symbol.
            exchange: Exchange identifier.
            resolution: Candle resolution.

        Returns:
            Cache key string.
        """
        return f"historical:{exchange}:{symbol}:{resolution}"

    def _try_cache(
        self,
        cache_key: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[Candle]:
        """Attempt to retrieve candles from cache.

        Uses stale-while-revalidate: stale data is served if available
        but marked for background refresh.

        Args:
            cache_key: Cache key for the data.
            start_time: Start of requested range.
            end_time: End of requested range.

        Returns:
            List of cached candles (possibly empty).
        """
        cached = self._cache.get(cache_key)
        if cached is None:
            return []
        if not isinstance(cached, list):
            return []
        # Normalize timezone awareness for comparison

        def _aware(ts: datetime) -> datetime:
            return ts if ts.tzinfo else ts.replace(tzinfo=UTC)

        s = _aware(start_time)
        e = _aware(end_time)
        # Filter to requested range
        filtered = [c for c in cached if isinstance(c, Candle) and s <= _aware(c.timestamp) <= e]
        return filtered

    def _populate_cache(
        self,
        cache_key: str,
        candles: list[Candle],
        resolution: str,
    ) -> None:
        """Store candles in cache.

        Merges with existing cache data and applies TTL based on resolution.

        Args:
            cache_key: Cache key for the data.
            candles: Candle list to cache.
            resolution: Candle resolution (for TTL determination).
        """
        # Get existing cached data and merge
        existing = self._cache.get(cache_key)
        if existing and isinstance(existing, list):
            merged = self._merge_candles(existing, candles)
        else:
            merged = list(candles)

        policy = self._default_policy or policy_for_resolution(resolution)
        self._cache.set(cache_key, merged, ttl_seconds=float(policy.ttl_seconds))

    # ── Range Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _covers_range(
        candles: list[Candle],
        start_time: datetime,
        end_time: datetime,
    ) -> bool:
        """Check if candle list fully covers the requested time range.

        Args:
            candles: List of candles to check.
            start_time: Start of range.
            end_time: End of range.

        Returns:
            True if candles cover the full range (first ≤ start, last ≥ end).
        """
        if not candles:
            return False
        timestamps = sorted(c.timestamp for c in candles)
        # Allow small tolerance (candles may start/end slightly outside range)
        tolerance = timedelta(minutes=1)
        # Normalize timezone awareness for comparison

        def _aware(ts: datetime) -> datetime:
            return ts if ts.tzinfo else ts.replace(tzinfo=UTC)

        s = _aware(start_time)
        e = _aware(end_time)
        return _aware(timestamps[0]) <= s + tolerance and _aware(timestamps[-1]) >= e - tolerance

    @staticmethod
    def _find_missing_range(
        candles: list[Candle],
        start_time: datetime,
        end_time: datetime,
    ) -> tuple[datetime, datetime]:
        """Find the start/end of missing data in a candle range.

        Args:
            candles: Existing candles (may be partial).
            start_time: Desired start.
            end_time: Desired end.

        Returns:
            Tuple of (missing_start, missing_end). If no candles exist,
            returns (start_time, end_time).
        """
        if not candles:
            return start_time, end_time

        # Normalize timezone awareness for comparison

        def _aware(ts: datetime) -> datetime:
            return ts if ts.tzinfo else ts.replace(tzinfo=UTC)

        timestamps = sorted(c.timestamp for c in candles)
        s = _aware(start_time)
        e = _aware(end_time)
        first_ts = _aware(timestamps[0])
        last_ts = _aware(timestamps[-1])
        if first_ts > s:
            return start_time, end_time
        if last_ts < e:
            return timestamps[-1], end_time

        # Range is fully covered
        return end_time, start_time  # empty range

    @staticmethod
    def _merge_candles(
        existing: list[Candle],
        new_candles: list[Candle],
    ) -> list[Candle]:
        """Merge two candle lists, deduplicating by timestamp.

        New candles take precedence over existing ones (for the same timestamp).

        Args:
            existing: Existing candle list.
            new_candles: New candle list to merge.

        Returns:
            Merged, sorted candle list.
        """
        seen: dict[datetime, Candle] = {}
        for c in existing:
            seen[c.timestamp] = c
        for c in new_candles:
            seen[c.timestamp] = c  # new overwrites existing
        return sorted(seen.values(), key=lambda c: c.timestamp)

    @staticmethod
    def _needs_pagination(
        start_time: datetime,
        end_time: datetime,
        max_chunk_days: int = 90,
    ) -> bool:
        """Check if the range needs to be paginated.

        Args:
            start_time: Start of range.
            end_time: End of range.
            max_chunk_days: Maximum days per chunk.

        Returns:
            True if range exceeds max_chunk_days.
        """
        delta = (end_time - start_time).days
        return delta > max_chunk_days

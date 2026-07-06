"""CachedDecorator — caches quote and LTP data with configurable TTL.

Reduces broker API calls for frequently-quoted instruments by serving
cached values within a configurable time window. Useful for:

- Dashboards that poll ``quote()`` every frame
- Strategies that reference the same instrument in multiple places
- Reducing rate-limit pressure on broker APIs

Usage::

    from brokers.market.cache_decorator import CachedDecorator

    inst = CachedDecorator(base_instrument, ttl_seconds=2.0)
    inst.quote()  # → fetches fresh, caches result
    inst.quote()  # → returns cached (within TTL)
    inst.ltp()    # → returns cached (within TTL)
"""

from __future__ import annotations

import time
from decimal import Decimal

from brokers.domain.entities import Quote
from brokers.market.decorators import InstrumentDecorator
from brokers.market.instrument import Instrument


class CachedDecorator(InstrumentDecorator):
    """Wraps an Instrument to cache quote/LTP data for a configurable TTL.

    Attributes:
        _wrapped: The underlying Instrument (via InstrumentDecorator).
        _ttl: Cache time-to-live in seconds.
        _quote_cache: Last cached Quote (or None).
        _quote_cached_at: Monotonic timestamp of last quote fetch.
        _ltp_cache: Last cached LTP (or None).
        _ltp_cached_at: Monotonic timestamp of last LTP fetch.
    """

    def __init__(self, instrument: Instrument, ttl_seconds: float = 2.0) -> None:
        super().__init__(instrument)
        object.__setattr__(self, "_ttl", ttl_seconds)
        object.__setattr__(self, "_quote_cache", None)
        object.__setattr__(self, "_quote_cached_at", 0.0)
        object.__setattr__(self, "_ltp_cache", None)
        object.__setattr__(self, "_ltp_cached_at", 0.0)

    def quote(self) -> Quote:
        """Get current quote with caching.

        Returns cached quote if within TTL, otherwise fetches fresh
        from the wrapped instrument and updates the cache.
        """
        now = time.monotonic()
        cache = self._quote_cache
        if cache is not None and (now - self._quote_cached_at) < self._ttl:
            return cache
        result = self._wrapped.quote()
        object.__setattr__(self, "_quote_cache", result)
        object.__setattr__(self, "_quote_cached_at", now)
        return result

    def ltp(self) -> Decimal:
        """Get last traded price with caching.

        Returns cached LTP if within TTL, otherwise fetches fresh.
        """
        now = time.monotonic()
        cache = self._ltp_cache
        if cache is not None and (now - self._ltp_cached_at) < self._ttl:
            return cache
        result = self._wrapped.ltp()
        object.__setattr__(self, "_ltp_cache", result)
        object.__setattr__(self, "_ltp_cached_at", now)
        return result

    def invalidate(self) -> None:
        """Force cache invalidation. Next call will fetch fresh data."""
        object.__setattr__(self, "_quote_cache", None)
        object.__setattr__(self, "_quote_cached_at", 0.0)
        object.__setattr__(self, "_ltp_cache", None)
        object.__setattr__(self, "_ltp_cached_at", 0.0)

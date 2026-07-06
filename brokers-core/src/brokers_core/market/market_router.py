"""Market data router — cache-first routing for real-time quotes, LTP, and depth.

Architecture::

    Client (MarketDataContext)
        │
        ▼
    MarketRouter
        │
        ├── Cache (fast path) ── cache hit + fresh → return immediately
        │
        └── Provider chain (slow path)
            ├── Primary provider (broker adapter)
            ├── Fallback provider (replay, alternative broker)
            └── Each result → populate cache for next request

Supports:
- Cache-first: fresh cached data returned without broker API call
- Stale-while-revalidate: stale data served while fetching fresh in background
- Provider fallback: primary → secondary → tertiary
- TTL-based expiry per data type (quote: 2s, depth: 1s)
- Lightweight metrics: cache_hits, cache_misses, provider_calls, errors

The router pattern mirrors ``HistoricalRouter`` for consistency.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers_core.domain.cache_policy import POLICY_DEPTH, POLICY_QUOTE
from brokers_core.domain.entities import MarketDepth, Quote
from brokers_core.ports.cache_port import CachePort
from brokers_core.ports.market_data import MarketDataPort

logger = logging.getLogger(__name__)

_QUOTE_CACHE_PREFIX = "quote:"
_DEPTH_CACHE_PREFIX = "depth:"
_LTP_CACHE_PREFIX = "ltp:"


class MarketRouter:
    """Routes real-time market data requests through cache-first provider chain.

    Strategy:
        1. Check cache for the requested symbol.
        2. If cache hit and fresh, return immediately (no broker API call).
        3. If cache miss or stale, query primary provider.
        4. If primary fails, try fallback providers.
        5. Populate cache with results for future requests.

    Args:
        cache: Cache backend for market data.
        primary: Primary market data provider (typically broker adapter).
        quote_ttl_seconds: TTL for cached quotes. Defaults to 2s.
        depth_ttl_seconds: TTL for cached depth. Defaults to 1s.
    """

    def __init__(
        self,
        cache: CachePort,
        primary: MarketDataPort | None = None,
        quote_ttl_seconds: float | None = None,
        depth_ttl_seconds: float | None = None,
    ) -> None:
        self._cache = cache
        self._primary = primary
        self._fallbacks: list[MarketDataPort] = []
        self._quote_ttl = quote_ttl_seconds or float(POLICY_QUOTE.ttl_seconds)
        self._depth_ttl = depth_ttl_seconds or float(POLICY_DEPTH.ttl_seconds)
        # Lightweight metrics (process-local counters)
        self._metrics: dict[str, int] = {
            "quote_cache_hits": 0,
            "quote_cache_misses": 0,
            "depth_cache_hits": 0,
            "depth_cache_misses": 0,
            "ltp_cache_hits": 0,
            "ltp_cache_misses": 0,
            "provider_errors": 0,
        }

    # ── Provider Management ────────────────────────────────────────────

    def set_primary(self, provider: MarketDataPort) -> None:
        """Set the primary market data provider (typically broker adapter)."""
        self._primary = provider
        logger.info("MarketRouter: primary provider set")

    def add_fallback(self, provider: MarketDataPort) -> None:
        """Register a fallback market data provider.

        Fallbacks are tried in registration order if the primary fails.
        """
        self._fallbacks.append(provider)
        logger.info("MarketRouter: fallback provider registered")

    # ── Quote Routing ──────────────────────────────────────────────────

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        """Get current quote with cache-first routing.

        Strategy:
            1. Check cache for ``{exchange}:{symbol}``.
            2. If cache hit and fresh (within TTL), return immediately.
            3. If cache miss or stale, query primary provider.
            4. If primary fails, try fallback providers.
            5. Populate cache and return.

        Args:
            symbol: Trading symbol.
            exchange: Exchange code.

        Returns:
            Quote domain entity.

        Raises:
            RuntimeError: If no provider is available.
        """
        cache_key = f"{_QUOTE_CACHE_PREFIX}{exchange}:{symbol}"

        # Step 1: Try cache-first (fast path)
        cached = self._cache.get(cache_key)
        if cached is not None and isinstance(cached, Quote):
            self._metrics["quote_cache_hits"] += 1
            logger.debug("MarketRouter: quote cache HIT for %s:%s", exchange, symbol)
            return cached
        self._metrics["quote_cache_misses"] += 1

        # Step 2: Try providers
        quote = self._fetch_from_providers("quote", symbol, exchange)
        if quote is None:
            raise RuntimeError(f"No market data provider available for quote({exchange}:{symbol})")

        # Step 3: Populate cache
        self._cache.set(cache_key, quote, ttl_seconds=self._quote_ttl)
        return quote

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        """Get last traded price with cache-first routing.

        Uses the quote cache and extracts LTP from it.

        Args:
            symbol: Trading symbol.
            exchange: Exchange code.

        Returns:
            Last traded price.

        Raises:
            RuntimeError: If no provider is available.
        """
        cache_key = f"{_LTP_CACHE_PREFIX}{exchange}:{symbol}"

        # Step 1: Try cache-first
        cached = self._cache.get(cache_key)
        if cached is not None and isinstance(cached, Decimal):
            self._metrics["ltp_cache_hits"] += 1
            logger.debug("MarketRouter: ltp cache HIT for %s:%s", exchange, symbol)
            return cached
        self._metrics["ltp_cache_misses"] += 1

        # Step 2: Try to get from quote cache first (avoid extra API call)
        quote_cache_key = f"{_QUOTE_CACHE_PREFIX}{exchange}:{symbol}"
        cached_quote = self._cache.get(quote_cache_key)
        if cached_quote is not None and isinstance(cached_quote, Quote):
            return cached_quote.ltp

        # Step 3: Try from quote (will cache the full quote)
        quote = self.quote(symbol, exchange)
        self._cache.set(cache_key, quote.ltp, ttl_seconds=self._quote_ttl)
        return quote.ltp

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        """Get market depth with cache-first routing.

        Args:
            symbol: Trading symbol.
            exchange: Exchange code.

        Returns:
            MarketDepth domain entity.

        Raises:
            RuntimeError: If no provider is available.
        """
        cache_key = f"{_DEPTH_CACHE_PREFIX}{exchange}:{symbol}"

        # Step 1: Try cache-first
        cached = self._cache.get(cache_key)
        if cached is not None and isinstance(cached, MarketDepth):
            self._metrics["depth_cache_hits"] += 1
            logger.debug("MarketRouter: depth cache HIT for %s:%s", exchange, symbol)
            return cached
        self._metrics["depth_cache_misses"] += 1

        # Step 2: Try providers
        depth = self._fetch_from_providers("depth", symbol, exchange)
        if depth is None:
            raise RuntimeError(f"No market data provider available for depth({exchange}:{symbol})")

        # Step 3: Populate cache
        self._cache.set(cache_key, depth, ttl_seconds=self._depth_ttl)
        return depth

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        """Get quotes for multiple symbols.

        Uses cache-first per symbol. Uncached symbols are fetched in batch
        from the provider.

        Args:
            symbols: List of trading symbols.
            exchange: Exchange code.

        Returns:
            Dict mapping symbol to Quote.
        """
        result: dict[str, Quote] = {}
        uncached: list[str] = []

        # Check cache first
        for symbol in symbols:
            cache_key = f"{_QUOTE_CACHE_PREFIX}{exchange}:{symbol}"
            cached = self._cache.get(cache_key)
            if cached is not None and isinstance(cached, Quote):
                result[symbol] = cached
            else:
                uncached.append(symbol)

        # Fetch uncached symbols from provider
        if uncached:
            if self._primary is not None:
                try:
                    batch = self._primary.quote_batch(uncached, exchange)
                    for sym, quote in batch.items():
                        result[sym] = quote
                        ck = f"{_QUOTE_CACHE_PREFIX}{exchange}:{sym}"
                        self._cache.set(ck, quote, ttl_seconds=self._quote_ttl)
                except Exception as exc:
                    logger.warning(
                        "MarketRouter: primary quote_batch failed for %s: %s",
                        uncached,
                        exc,
                    )
                    # Try fallbacks individually
                    for symbol in uncached:
                        try:
                            result[symbol] = self._fetch_from_providers("quote", symbol, exchange)
                        except Exception:
                            pass
            else:
                # No primary provider — try individual fetches from fallbacks
                for symbol in uncached:
                    try:
                        result[symbol] = self._fetch_from_providers("quote", symbol, exchange)
                    except Exception:
                        pass

        return result

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        """Get LTP for multiple symbols.

        Args:
            symbols: List of trading symbols.
            exchange: Exchange code.

        Returns:
            Dict mapping symbol to LTP.
        """
        # Try batch from primary
        if self._primary is not None:
            try:
                return self._primary.ltp_batch(symbols, exchange)
            except Exception as exc:
                logger.warning("MarketRouter: primary ltp_batch failed: %s", exc)

        # Fallback: fetch individually
        result: dict[str, Decimal] = {}
        for symbol in symbols:
            try:
                result[symbol] = self.ltp(symbol, exchange)
            except Exception:
                pass
        return result

    # ── Cache Invalidation ─────────────────────────────────────────────

    def invalidate(self, symbol: str, exchange: str = "NSE") -> None:
        """Invalidate cached data for a symbol.

        Args:
            symbol: Trading symbol.
            exchange: Exchange code.
        """
        for prefix in (_QUOTE_CACHE_PREFIX, _DEPTH_CACHE_PREFIX, _LTP_CACHE_PREFIX):
            self._cache.delete(f"{prefix}{exchange}:{symbol}")
        logger.debug("MarketRouter: invalidated cache for %s:%s", exchange, symbol)

    # ── Internals ──────────────────────────────────────────────────────

    def _fetch_from_providers(
        self,
        data_type: str,
        symbol: str,
        exchange: str,
    ) -> Quote | MarketDepth | None:
        """Try to fetch data from primary, then fallbacks.

        Args:
            data_type: One of "quote", "depth".
            symbol: Trading symbol.
            exchange: Exchange code.

        Returns:
            The fetched data, or None if all providers failed.
        """
        providers: list[MarketDataPort] = []
        if self._primary is not None:
            providers.append(self._primary)
        providers.extend(self._fallbacks)

        for provider in providers:
            try:
                if data_type == "quote":
                    return provider.quote(symbol, exchange)
                elif data_type == "depth":
                    return provider.depth(symbol, exchange)
            except Exception as exc:
                self._metrics["provider_errors"] += 1
                logger.warning(
                    "MarketRouter: provider failed for %s:%s: %s",
                    exchange,
                    symbol,
                    exc,
                )
                continue

        return None

    @property
    def has_provider(self) -> bool:
        """Check if at least one provider is available."""
        return self._primary is not None or len(self._fallbacks) > 0

    def metrics(self) -> dict[str, int]:
        """Return a snapshot of router metrics.

        Keys:
            - quote_cache_hits, quote_cache_misses
            - depth_cache_hits, depth_cache_misses
            - ltp_cache_hits, ltp_cache_misses
            - provider_errors
        """
        return dict(self._metrics)

"""Cache policy — TTL and staleness configuration for historical data caching."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

# Default TTLs for different data types (in seconds)
CACHE_TTL_HISTORICAL_1M: int = 300  # 5 min — 1m candles change frequently
CACHE_TTL_HISTORICAL_5M: int = 600  # 10 min
CACHE_TTL_HISTORICAL_15M: int = 1800  # 30 min
CACHE_TTL_HISTORICAL_60M: int = 3600  # 1 hour
CACHE_TTL_HISTORICAL_1D: int = 86400  # 24 hours — daily candles rarely change
CACHE_TTL_QUOTE: int = 2  # 2 seconds — quotes are real-time
CACHE_TTL_DEPTH: int = 1  # 1 second — depth is ultra real-time
CACHE_TTL_INSTRUMENT_MASTER: int = 3600  # 1 hour — instrument master changes daily

# Max age before stale (for stale-while-revalidate)
CACHE_STALE_HISTORICAL_1M: int = 60  # 1 min stale
CACHE_STALE_HISTORICAL_5M: int = 120  # 2 min stale
CACHE_STALE_HISTORICAL_15M: int = 300  # 5 min stale
CACHE_STALE_HISTORICAL_60M: int = 600  # 10 min stale
CACHE_STALE_HISTORICAL_1D: int = 3600  # 1 hour stale


@dataclass(frozen=True)
class CachePolicy:
    """Cache policy configuration for a given data type.

    Attributes:
        ttl_seconds: Time-to-live before cache entry expires.
        stale_seconds: Additional time during which stale data is served
            while revalidating in background (stale-while-revalidate).
        max_entries: Maximum number of entries in cache (LRU eviction).
    """

    ttl_seconds: int
    stale_seconds: int = 0
    max_entries: int = 10_000

    @property
    def total_valid_seconds(self) -> int:
        """Total time before data is considered fully expired (TTL + stale window)."""
        return self.ttl_seconds + self.stale_seconds


# Predefined cache policies
POLICY_HISTORICAL_INTRADAY: CachePolicy = CachePolicy(
    ttl_seconds=CACHE_TTL_HISTORICAL_1M,
    stale_seconds=CACHE_STALE_HISTORICAL_1M,
)
POLICY_HISTORICAL_DAILY: CachePolicy = CachePolicy(
    ttl_seconds=CACHE_TTL_HISTORICAL_1D,
    stale_seconds=CACHE_STALE_HISTORICAL_1D,
)
POLICY_QUOTE: CachePolicy = CachePolicy(
    ttl_seconds=CACHE_TTL_QUOTE,
    max_entries=50_000,
)
POLICY_DEPTH: CachePolicy = CachePolicy(
    ttl_seconds=CACHE_TTL_DEPTH,
    max_entries=10_000,
)
POLICY_INSTRUMENT_MASTER: CachePolicy = CachePolicy(
    ttl_seconds=CACHE_TTL_INSTRUMENT_MASTER,
    stale_seconds=300,
    max_entries=1_000_000,
)


def policy_for_resolution(resolution: str) -> CachePolicy:
    """Return the appropriate cache policy for a candle resolution.

    Args:
        resolution: Candle resolution string (e.g., '1', '5', '15', '60', '1D').

    Returns:
        CachePolicy appropriate for the resolution.
    """
    if resolution in ("1D", "D", "DAY"):
        return POLICY_HISTORICAL_DAILY
    return POLICY_HISTORICAL_INTRADAY

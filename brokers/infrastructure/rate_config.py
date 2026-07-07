"""Per-endpoint rate limit configuration for broker HTTP clients.

Provides configurable rate limits matching the real API constraints
of Dhan and Upstox. Each broker has different limits per endpoint
category — a single global limiter would either throttle orders too
aggressively or allow market-data flooding.

Usage::

    from brokers.infrastructure.rate_config import DhanRateLimits

    config = DhanRateLimits()
    interval = config.get_interval("/marketfeed/quote")  # → 1.0 second
    category = config.categorize("/orders")               # → "write"
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ── Dhan Rate Limits (from Dhan API documentation) ─────────────────────────
#
# Non-Trading APIs: Up to 20 requests per second
# Order APIs: Up to 25 requests per second
# Data APIs: Up to 10 requests per second
# Quote APIs: 1 request per second (strictest)


DHAN_RATE_LIMITS: dict[str, float] = {
    "/marketfeed/quote": 1.0,       # 1 req/s — strictest
    "/marketfeed/ltp": 0.2,         # 5 req/s
    "/marketfeed/ohlc": 0.2,        # 5 req/s
    "/optionchain": 0.35,           # ~3 req/s
    "/charts/historical": 0.1,      # 10 req/s
    "/charts/intraday": 0.1,        # 10 req/s
    "/charts/": 0.1,                # 10 req/s (prefix fallback)
    "/orders": 0.04,               # 25 req/s
    "/trades": 0.04,               # 25 req/s
    "/positions": 0.05,            # ~20 req/s
    "/holdings": 0.05,             # ~20 req/s
    "/fundlimit": 0.05,            # ~20 req/s
}

DHAN_READ_PREFIXES: tuple[str, ...] = (
    "/marketfeed/ltp",
    "/marketfeed/quote",
    "/marketfeed/ohlc",
    "/charts/",
    "/optionchain",
    "/marketstatus",
    "/instruments",
)

DHAN_WRITE_PREFIXES: tuple[str, ...] = (
    "/orders",
    "/killswitch",
    "/sliceorder",
)


# ── Upstox Rate Limits (from Upstox API documentation) ─────────────────────
#
# Order Placement (Regular): 10 req/s
# Order Placement (SEBI-Registered Algo): 50 req/s
# Standard APIs (holdings, positions, funds, history, quotes): 50 req/s
# Payout APIs (read): 10 req/s
# Payout APIs (write): 10 req/min


UPSTOX_RATE_LIMITS: dict[str, float] = {
    "/v3/order/place": 0.1,           # 10 req/s — order placement
    "/v3/order/cancel": 0.1,          # 10 req/s
    "/v3/order/modify": 0.1,          # 10 req/s
    "/v3/order/": 0.1,                # 10 req/s (prefix for order endpoints)
    "/v3/trades/": 0.02,              # 50 req/s — standard API
    "/v3/market-quote/ltp": 0.02,     # 50 req/s — standard API
    "/v3/market-quote/quotes": 0.02,  # 50 req/s — standard API
    "/v3/market-quote/ohlc": 0.02,    # 50 req/s — standard API
    "/v3/market-quote/": 0.02,        # 50 req/s — standard API prefix
    "/v2/historical-candle/": 0.02,   # 50 req/s — standard API
    "/v2/option/chain": 0.02,         # 50 req/s — standard API
    "/v2/portfolio/": 0.02,           # 50 req/s — standard API
    "/v2/user/": 0.02,                # 50 req/s — standard API
}

UPSTOX_READ_PREFIXES: tuple[str, ...] = (
    "/v3/market-quote/",
    "/v2/historical-candle/",
    "/v2/option/",
    "/v2/market-status",
)

UPSTOX_WRITE_PREFIXES: tuple[str, ...] = (
    "/v3/order/place",
    "/v3/order/cancel",
    "/v3/order/modify",
)


# ── Rate Limit Config ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class RateLimitConfig:
    """Configurable per-endpoint rate limits with endpoint categorization.

    Attributes:
        limits: Dict mapping endpoint prefixes to minimum intervals (seconds).
        read_prefixes: Endpoint prefixes categorized as "read" (market data).
        write_prefixes: Endpoint prefixes categorized as "write" (orders).
    """

    limits: dict[str, float] = field(default_factory=dict)
    read_prefixes: tuple[str, ...] = ()
    write_prefixes: tuple[str, ...] = ()

    def get_interval(self, endpoint: str) -> float:
        """Get the minimum interval (seconds) between calls to *endpoint*.

        Matches exact endpoint first, then falls back to prefix matching.
        Returns 0.0 if no limit is configured for the endpoint.
        """
        if endpoint in self.limits:
            return self.limits[endpoint]
        for prefix, interval in self.limits.items():
            if endpoint.startswith(prefix):
                return interval
        return 0.0

    def categorize(self, endpoint: str) -> str:
        """Categorize an endpoint as 'read', 'write', or 'admin'.

        - 'write': order placement, modification, cancellation
        - 'read': market data, historical, option chain
        - 'admin': portfolio, account, token refresh (default)
        """
        for prefix in self.write_prefixes:
            if endpoint.startswith(prefix):
                return "write"
        for prefix in self.read_prefixes:
            if endpoint.startswith(prefix):
                return "read"
        return "admin"


# ── Pre-built configs ──────────────────────────────────────────────────────


def dhan_rate_config() -> RateLimitConfig:
    """Return rate limit config matching Dhan's documented API limits."""
    return RateLimitConfig(
        limits=dict(DHAN_RATE_LIMITS),
        read_prefixes=DHAN_READ_PREFIXES,
        write_prefixes=DHAN_WRITE_PREFIXES,
    )


def upstox_rate_config() -> RateLimitConfig:
    """Return rate limit config matching Upstox's documented API limits."""
    return RateLimitConfig(
        limits=dict(UPSTOX_RATE_LIMITS),
        read_prefixes=UPSTOX_READ_PREFIXES,
        write_prefixes=UPSTOX_WRITE_PREFIXES,
    )


__all__ = [
    "RateLimitConfig",
    "dhan_rate_config",
    "upstox_rate_config",
    "DHAN_RATE_LIMITS",
    "UPSTOX_RATE_LIMITS",
]

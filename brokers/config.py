"""Broker configuration — endpoints, defaults, and rate limit settings.

This module centralizes all configurable parameters. Broker adapters
import from here rather than hardcoding values.
"""

from __future__ import annotations

from dataclasses import dataclass


# ── Market data defaults ─────────────────────────────────────────────────────

DEFAULT_EXCHANGE = "NSE"
DEFAULT_DERIVATIVES_EXCHANGE = "NFO"
DEFAULT_LOOKBACK_DAYS = 90
DEFAULT_TIMEFRAME = "1D"

# ── Order defaults ───────────────────────────────────────────────────────────

DEFAULT_SIDE = "BUY"
DEFAULT_ORDER_TYPE = "MARKET"
DEFAULT_PRODUCT_TYPE = "INTRADAY"
DEFAULT_VALIDITY = "DAY"

# ── Stream defaults ──────────────────────────────────────────────────────────

DEFAULT_STREAM_MODE = "LTP"
DEFAULT_DEPTH_TYPE = "DEPTH_5"


@dataclass(frozen=True)
class DhanEndpoints:
    REST_BASE = "https://api.dhan.co/v2"
    GENERATE_TOKEN_URL = "https://api.dhan.co/v2/validate/auth/login"
    INSTRUMENT_CSV = "https://images.dhan.co/master/eqmaster.csv"
    INSTRUMENT_MCX_DETAILED = "https://images.dhan.co/master/commaster.csv"
    SLICE_ORDER = "https://api.dhan.co/v2/orders/slice"
    WS_DEPTH_20 = "wss://feed.dhan.co/websocket/NestFeed"
    WS_DEPTH_200 = "wss://feed.dhan.co/websocket/NestFeed"
    WS_MARKET = "wss://feed.dhan.co/websocket/NestFeed"


@dataclass(frozen=True)
class UpstoxEndpoints:
    REST_BASE = "https://api.upstox.com/v2"
    AUTHORIZE = "https://api.upstox.com/v2/login/authorization/dialog"
    TOKEN = "https://api.upstox.com/v2/login/authorization/token"
    PROFILE = "https://api.upstox.com/v2/user/profile"
    ORDERS = "https://api.upstox.com/v2/order/place"
    CANCEL = "https://api.upstox.com/v2/order/cancel"
    LTP = "https://api.upstox.com/v2/market-quote/ltp"
    QUOTE = "https://api.upstox.com/v2/market-quote/quotes"
    OHLC = "https://api.upstox.com/v2/market-quote/ohlc"
    HISTORICAL = "https://api.upstox.com/v2/historical-candle"
    WS_MARKET = "wss://ws.upstox.com/market/feed/v1"
    WS_ORDER = "wss://ws.upstox.com/order/feed/v1"


@dataclass(frozen=True)
class RateLimitConfig:
    rate_per_second: float = 10.0
    capacity: int = 10


@dataclass(frozen=True)
class RetryConfig:
    max_retries: int = 3
    base_delay_ms: int = 500
    max_delay_ms: int = 5000


@dataclass(frozen=True)
class CircuitBreakerConfig:
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    success_threshold: int = 1

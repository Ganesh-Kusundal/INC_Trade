"""Constants package — re-exports all constants for backward compatibility."""

from __future__ import annotations

from brokers.domain.constants.broker_ids import (
    DHAN_ID,
    PAPER_ID,
    UPSTOX_ID,
)
from brokers.domain.constants.exchanges import (
    DEFAULT_DERIVATIVE_EXCHANGE,
    DEFAULT_EQUITY_EXCHANGE,
    DERIVATIVE_EXCHANGES,
    EQUITY_EXCHANGES,
)
from brokers.domain.constants.segments import SEGMENT_TO_EXCHANGE, SegmentResolver
from brokers.domain.constants.timeouts import (
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    DEFAULT_IDEMPOTENCY_TTL_SECONDS,
    DEFAULT_MAX_RECONNECT_DELAY,
    DEFAULT_RECONNECT_DELAY,
    DEFAULT_STOP_TIMEOUT_SECONDS,
    DEFAULT_TOKEN_LIFETIME_SECONDS,
    MIN_SLEEP_SECONDS,
)

__all__ = [
    "DEFAULT_DERIVATIVE_EXCHANGE",
    "DEFAULT_EQUITY_EXCHANGE",
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    "DEFAULT_IDEMPOTENCY_TTL_SECONDS",
    "DEFAULT_MAX_RECONNECT_DELAY",
    "DEFAULT_RECONNECT_DELAY",
    "DEFAULT_STOP_TIMEOUT_SECONDS",
    "DEFAULT_TOKEN_LIFETIME_SECONDS",
    "DERIVATIVE_EXCHANGES",
    "DHAN_ID",
    "EQUITY_EXCHANGES",
    "MIN_SLEEP_SECONDS",
    "PAPER_ID",
    "SEGMENT_TO_EXCHANGE",
    "SegmentResolver",
    "UPSTOX_ID",
]

"""Constants package — re-exports all constants for backward compatibility.

This package splits the monolithic constants.py into focused sub-modules:
- timeouts: Stop timeouts, HTTP timeouts, sleep intervals
- resilience: Retry, circuit breaker, backoff configuration
- auth: Token lifecycle and authentication constants
- risk: Risk thresholds, position limits, capital defaults
- market: Market hours, exchanges, tick sizes, timezone
- observability: HTTP server configuration

All constants are re-exported here to maintain backward compatibility with
existing imports from ``brokers.common.core.constants``.
"""

from __future__ import annotations

from domain.constants.auth import (
    DHAN_REFRESH_COOLDOWN_SECONDS,
    DHAN_TOKEN_LIFETIME_SECONDS,
    DHAN_TOKEN_REFRESH_BUFFER_SECONDS,
    DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS,
    TOKEN_CLOCK_SKEW_SECONDS,
    TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS,
)
from domain.constants.defaults import DEFAULT_LOOKBACK_DAYS
from domain.constants.exchanges import (
    BCD,
    BFO,
    BSE,
    CDS,
    IDX,
    MCX,
    NFO,
    NSE,
    WIRE_BSE_CURRENCY,
    WIRE_BSE_EQ,
    WIRE_BSE_FNO,
    WIRE_IDX,
    WIRE_MCX_COMM,
    WIRE_NSE_CURRENCY,
    WIRE_NSE_EQ,
    WIRE_NSE_FNO,
)
from domain.constants.market import (
    ATR_PERIOD_DEFAULT,
    DEFAULT_DERIVATIVES_EXCHANGE,
    DEFAULT_EXCHANGE,
    DEFAULT_EXCHANGE_SEGMENT_FALLBACK,
    DEFAULT_TICK_SIZE,
    IST_OFFSET,
    MCX_CLOSE_HOUR_IST,
    MCX_CLOSE_MINUTE_IST,
    MCX_OPEN_HOUR_IST,
    MCX_OPEN_MINUTE_IST,
    NSE_CLOSE_HOUR_IST,
    NSE_CLOSE_MINUTE_IST,
    NSE_OPEN_HOUR_IST,
    NSE_OPEN_MINUTE_IST,
    RSI_PERIOD_DEFAULT,
    SMA_WINDOW_DEFAULT,
)
from domain.constants.observability import (
    OBSERVABILITY_DEFAULT_HOST,
    OBSERVABILITY_DEFAULT_PORT,
)
from domain.constants.resilience import (
    BACKOFF_JITTER,
    BACKOFF_MULTIPLIER,
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    CIRCUIT_BREAKER_OPEN_DURATION_MS,
    CIRCUIT_BREAKER_SUCCESS_THRESHOLD,
    MAX_RETRY_ATTEMPTS,
    MAX_RETRY_DELAY_MS,
    RETRY_BASE_DELAY_MS,
)
from domain.constants.risk import (
    DHAN_NOTIONAL_WARNING_INR,
    PHANTOM_CAPITAL_INR,
    RISK_DAILY_LOSS_PERCENT,
    RISK_GROSS_PERCENT,
    RISK_LOSS_CB_COOLDOWN_SECONDS,
    RISK_LOSS_CB_WINDOW_SECONDS,
    RISK_LOSS_CIRCUIT_BREAKER_PERCENT,
    RISK_MARGIN_SAFETY_MULTIPLIER,
    RISK_POSITION_PERCENT,
)
from domain.constants.timeouts import (
    DEFAULT_HTTP_TIMEOUT_SECONDS,
    DEFAULT_STOP_TIMEOUT_SECONDS,
    HISTORY_CACHE_TTL_SECONDS,
    MIN_SLEEP_SECONDS,
    QUOTE_CACHE_TTL_SECONDS,
)

# ── OMS / reconciliation cadence (not yet split) ──────────────────────────

#: Reconciliation cycle (seconds). Used by TradingContext, factory,
#: and ReconciliationService default.
RECONCILIATION_INTERVAL_SECONDS: float = 300.0

#: Daily-PnL reset poll interval (seconds). Used by
#: DailyPnlResetScheduler.
DAILY_PNL_POLL_INTERVAL_SECONDS: float = 60.0

#: Default rollover hour in IST (0 = midnight). Used by
#: DailyPnlResetScheduler.
DAILY_PNL_ROLLOVER_HOUR_IST: int = 0

#: Number of days the ProcessedTradeRepository retains trade IDs in
#: memory before cleanup() may evict them.
PROCESSED_TRADE_RETENTION_SECONDS: int = 24 * 60 * 60  # 86_400

#: Periodic cleanup interval for ProcessedTradeRepository.
PROCESSED_TRADE_CLEANUP_INTERVAL_SECONDS: int = 60 * 60  # 1h

# ── Batching / threading ───────────────────────────────────────────────────

#: Number of worker threads used by BatchFetchMixin.
BATCH_MAX_WORKERS: int = 5

# ── Dead-letter queue ──────────────────────────────────────────────────────

#: Maximum events the DeadLetterQueue will buffer before dropping the
#: oldest. Larger values consume more memory.
DEAD_LETTER_QUEUE_MAX_SIZE: int = 10_000

# ── Log / instrumentation ──────────────────────────────────────────────────

#: Default log level used by :func:`brokers.common.logging_config.setup_logging`.
DEFAULT_LOG_LEVEL: str = "INFO"

#: Default log level for noisy third-party loggers.
THIRD_PARTY_LOG_LEVEL: str = "WARNING"

# ── History defaults ───────────────────────────────────────────────────────

#: Default pagination window for historical candle downloads (days).
DEFAULT_HISTORY_PAGE_DAYS: int = 365

#: BrokerCapabilities default for max intraday history (days).
DEFAULT_MAX_INTRADAY_DAYS: int = 90

#: BrokerCapabilities default for max multi-day history (days).
DEFAULT_MAX_DAILY_DAYS: int = 365 * 10

__all__ = [
    "ATR_PERIOD_DEFAULT",
    "BACKOFF_JITTER",
    "BACKOFF_MULTIPLIER",
    # batching
    "BATCH_MAX_WORKERS",
    "BCD",
    "BFO",
    "BSE",
    "CDS",
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD",
    "CIRCUIT_BREAKER_OPEN_DURATION_MS",
    "CIRCUIT_BREAKER_SUCCESS_THRESHOLD",
    "DAILY_PNL_POLL_INTERVAL_SECONDS",
    "DAILY_PNL_ROLLOVER_HOUR_IST",
    # DLQ
    "DEAD_LETTER_QUEUE_MAX_SIZE",
    "DEFAULT_DERIVATIVES_EXCHANGE",
    "DEFAULT_EXCHANGE",
    "DEFAULT_EXCHANGE_SEGMENT_FALLBACK",
    # history
    "DEFAULT_HISTORY_PAGE_DAYS",
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    # logging
    "DEFAULT_LOG_LEVEL",
    "DEFAULT_LOOKBACK_DAYS",
    "DEFAULT_MAX_DAILY_DAYS",
    "DEFAULT_MAX_INTRADAY_DAYS",
    # timeouts
    "DEFAULT_STOP_TIMEOUT_SECONDS",
    "DEFAULT_TICK_SIZE",
    "DHAN_NOTIONAL_WARNING_INR",
    "DHAN_REFRESH_COOLDOWN_SECONDS",
    "DHAN_TOKEN_LIFETIME_SECONDS",
    "DHAN_TOKEN_REFRESH_BUFFER_SECONDS",
    "DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS",
    "HISTORY_CACHE_TTL_SECONDS",
    "IDX",
    "IST_OFFSET",
    "MAX_RETRY_ATTEMPTS",
    # resilience
    "MAX_RETRY_DELAY_MS",
    "MCX",
    "MCX_CLOSE_HOUR_IST",
    "MCX_CLOSE_MINUTE_IST",
    "MCX_OPEN_HOUR_IST",
    "MCX_OPEN_MINUTE_IST",
    "MIN_SLEEP_SECONDS",
    "NFO",
    # exchanges
    "NSE",
    "NSE_CLOSE_HOUR_IST",
    "NSE_CLOSE_MINUTE_IST",
    "NSE_OPEN_HOUR_IST",
    "NSE_OPEN_MINUTE_IST",
    # observability
    "OBSERVABILITY_DEFAULT_HOST",
    "OBSERVABILITY_DEFAULT_PORT",
    "PHANTOM_CAPITAL_INR",
    "PROCESSED_TRADE_CLEANUP_INTERVAL_SECONDS",
    "PROCESSED_TRADE_RETENTION_SECONDS",
    "QUOTE_CACHE_TTL_SECONDS",
    # OMS
    "RECONCILIATION_INTERVAL_SECONDS",
    "RETRY_BASE_DELAY_MS",
    # risk
    "RISK_DAILY_LOSS_PERCENT",
    "RISK_GROSS_PERCENT",
    "RISK_LOSS_CB_COOLDOWN_SECONDS",
    "RISK_LOSS_CB_WINDOW_SECONDS",
    "RISK_LOSS_CIRCUIT_BREAKER_PERCENT",
    "RISK_MARGIN_SAFETY_MULTIPLIER",
    "RISK_POSITION_PERCENT",
    "RSI_PERIOD_DEFAULT",
    "SMA_WINDOW_DEFAULT",
    "THIRD_PARTY_LOG_LEVEL",
    "TOKEN_CLOCK_SKEW_SECONDS",
    # auth
    "TOKEN_REFRESH_RECOMMENDED_BUFFER_SECONDS",
    "WIRE_BSE_CURRENCY",
    "WIRE_BSE_EQ",
    "WIRE_BSE_FNO",
    "WIRE_IDX",
    "WIRE_MCX_COMM",
    "WIRE_NSE_CURRENCY",
    "WIRE_NSE_EQ",
    "WIRE_NSE_FNO",
]

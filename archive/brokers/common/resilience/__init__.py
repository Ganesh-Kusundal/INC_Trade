"""Resilience module — rate limiting, circuit breakers, retry with backoff."""

from __future__ import annotations

from brokers.common.resilience.backoff import (
    BackoffStrategy,
    ExponentialBackoff,
    FixedBackoff,
    NoBackoff,
)
from brokers.common.resilience.broker_health_monitor import (
    BrokerHealthMonitor,
    BrokerHealthStatus,
)
from brokers.common.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
)
from brokers.common.resilience.errors import (
    AuthenticationError,
    BrokerDegradedError,
    BrokerError,
    CircuitBreakerOpenError,
    ConfigError,
    DataError,
    InstrumentNotFoundError,
    NonRetryableError,
    NotSupportedError,
    OrderError,
    RateLimitError,
    RetryableError,
    TradeXV2Error,
    ValidationError,
)
from brokers.common.resilience.rate_limiter import (
    MultiBucketRateLimiter,
    RateLimitConfig,
    TokenBucketRateLimiter,
)
from brokers.common.resilience.retry import DEFAULT_RETRYABLE_EXCEPTIONS, RetryConfig, RetryExecutor

__all__ = [
    "DEFAULT_RETRYABLE_EXCEPTIONS",
    "AuthenticationError",
    "BackoffStrategy",
    "BrokerDegradedError",
    "BrokerError",
    "BrokerHealthMonitor",
    "BrokerHealthStatus",
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerOpenError",
    "CircuitState",
    "ConfigError",
    "DataError",
    "ExponentialBackoff",
    "FixedBackoff",
    "InstrumentNotFoundError",
    "MultiBucketRateLimiter",
    "NoBackoff",
    "NonRetryableError",
    "NotSupportedError",
    "OrderError",
    "RateLimitConfig",
    "RateLimitError",
    "RetryConfig",
    "RetryExecutor",
    "RetryableError",
    "TokenBucketRateLimiter",
    "TradeXV2Error",
    "ValidationError",
]

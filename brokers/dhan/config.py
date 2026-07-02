"""Dhan broker runtime configuration dataclasses.

Centralizes all configurable parameters for Dhan broker resilience patterns.
All hardcoded values from http_client.py are moved here for runtime configuration.

Design Principles:
  - Dataclasses for type safety and immutability
  - Environment variable overrides via config_loader.py
  - Backwards compatibility with existing defaults
  - Clean separation of concerns (rate limits, retries, circuit breakers)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from config.endpoints import Dhan


# ── Default base URL ─────────────────────────────────────────────────────────
DEFAULT_BASE_URL = Dhan.REST_BASE


# ── Rate Limit Defaults (from Dhan API documentation) ────────────────────────
# Non-Trading APIs: Up to 20 requests per second
# Order APIs: Up to 25 requests per second
# Data APIs: Up to 10 requests per second
# Quote APIs: 1 request per second

DEFAULT_RATE_LIMITS: dict[str, float] = {
    "/marketfeed/quote": 1.0,
    "/marketfeed/ltp": 0.15,  # Data APIs: up to 10 req/s
    "/marketfeed/ohlc": 0.15,  # 10 req/s documented
    "/optionchain": 0.35,  # 10 req/s documented
    "/charts/": 0.15,  # 10 req/s documented
    "/orders": 0.04,  # 25 req/s documented
}


# ── Circuit Breaker Prefixes ────────────────────────────────────────────────

DEFAULT_READ_CB_PREFIXES: tuple[str, ...] = (
    "/marketfeed/ltp",
    "/marketfeed/quote",
    "/marketfeed/ohlc",
    "/charts/",
    "/optionchain",
    "/marketstatus",
    "/instruments",
)

DEFAULT_WRITE_CB_PREFIXES: tuple[str, ...] = (
    "/orders",
    "/killswitch",
    "/sliceorder",
)

# Circuit breaker category to rate limiter bucket mapping
DEFAULT_RL_BUCKET_MAP: dict[str, str] = {
    "read": "market_data",
    "write": "orders",
    "admin": "admin",
}


# ── Retry Configuration Defaults ────────────────────────────────────────────
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY_MS = 500
DEFAULT_MAX_DELAY_MS = 5000


# ── Token Refresh Configuration ──────────────────────────────────────────────
DEFAULT_REFRESH_COOLDOWN_SECONDS = 60
DEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 130  # Dhan's 2-min rate limit + 10s buffer


@dataclass(frozen=True)
class DhanRateLimitConfig:
    """Configuration for Dhan API rate limiting.

    Attributes:
        limits: Dictionary mapping endpoint prefixes to minimum intervals (seconds).
            Used for throttling between requests to the same endpoint.
        read_prefixes: Endpoint prefixes categorized as "read" operations.
        write_prefixes: Endpoint prefixes categorized as "write" operations.
        bucket_map: Mapping from circuit breaker categories to rate limiter buckets.
    """

    limits: dict[str, float] = field(default_factory=lambda: DEFAULT_RATE_LIMITS.copy())
    read_prefixes: tuple[str, ...] = DEFAULT_READ_CB_PREFIXES
    write_prefixes: tuple[str, ...] = DEFAULT_WRITE_CB_PREFIXES
    bucket_map: dict[str, str] = field(default_factory=lambda: DEFAULT_RL_BUCKET_MAP.copy())

    def get_endpoint_interval(self, endpoint: str) -> float:
        """Get the rate limit interval for a specific endpoint."""
        if endpoint in self.limits:
            return self.limits[endpoint]
        for prefix, interval in self.limits.items():
            if endpoint.startswith(prefix):
                return interval
        return 0


@dataclass(frozen=True)
class DhanRetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts for failed requests.
        base_delay_ms: Base delay for exponential backoff (milliseconds).
        max_delay_ms: Maximum delay for exponential backoff (milliseconds).
    """

    max_retries: int = DEFAULT_MAX_RETRIES
    base_delay_ms: int = DEFAULT_BASE_DELAY_MS
    max_delay_ms: int = DEFAULT_MAX_DELAY_MS

    def calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff delay in seconds.

        Args:
            attempt: The current retry attempt number (1-indexed).

        Returns:
            Delay in seconds, capped at max_delay_ms.
        """
        delay_ms = min(self.base_delay_ms * (2 ** (attempt - 1)), self.max_delay_ms)
        return delay_ms / 1000.0


@dataclass(frozen=True)
class DhanCircuitBreakerConfig:
    """Configuration for circuit breaker behavior.

    Attributes:
        read_prefixes: Endpoint prefixes for read circuit breaker category.
        write_prefixes: Endpoint prefixes for write circuit breaker category.
        orders_failure_threshold: Failure threshold for orders circuit breaker.
        default_failure_threshold: Failure threshold for other circuit breakers.
        recovery_timeout_ms: Time in milliseconds before circuit breaker attempts recovery.
        success_threshold: Number of consecutive successes to close half-open circuit.
    """

    read_prefixes: tuple[str, ...] = DEFAULT_READ_CB_PREFIXES
    write_prefixes: tuple[str, ...] = DEFAULT_WRITE_CB_PREFIXES
    orders_failure_threshold: int = 3
    default_failure_threshold: int = 5
    recovery_timeout_ms: int = 30_000  # 30 seconds
    success_threshold: int = 3

    def categorize_endpoint(self, endpoint: str) -> str:
        """Categorize an endpoint for circuit breaker routing.

        Args:
            endpoint: The API endpoint path.

        Returns:
            One of 'read', 'write', or 'admin'.
        """
        for prefix in self.write_prefixes:
            if endpoint.startswith(prefix):
                return "write"
        for prefix in self.read_prefixes:
            if endpoint.startswith(prefix):
                return "read"
        return "admin"


@dataclass(frozen=True)
class DhanTokenConfig:
    """Configuration for token refresh behavior.

    Attributes:
        refresh_cooldown_seconds: Minimum time between token refresh attempts.
        rate_limit_backoff_seconds: Backoff time when Dhan rate limits token generation.
    """

    refresh_cooldown_seconds: float = DEFAULT_REFRESH_COOLDOWN_SECONDS
    rate_limit_backoff_seconds: float = DEFAULT_RATE_LIMIT_BACKOFF_SECONDS


@dataclass(frozen=True)
class DhanResilienceConfig:
    """Aggregated configuration for all Dhan resilience patterns.

    Combines rate limiting, retry, circuit breaker, and token configurations
    into a single, injectable configuration object.

    Attributes:
        rate_limit: Rate limit configuration.
        retry: Retry configuration.
        circuit_breaker: Circuit breaker configuration.
        token: Token refresh configuration.
        base_url: Base URL for Dhan API.
    """

    rate_limit: DhanRateLimitConfig = field(default_factory=DhanRateLimitConfig)
    retry: DhanRetryConfig = field(default_factory=DhanRetryConfig)
    circuit_breaker: DhanCircuitBreakerConfig = field(default_factory=DhanCircuitBreakerConfig)
    token: DhanTokenConfig = field(default_factory=DhanTokenConfig)
    base_url: str = DEFAULT_BASE_URL

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None = None) -> "DhanResilienceConfig":
        """Create configuration from a dictionary of values.

        Args:
            data: Dictionary with configuration values. Missing keys use defaults.

        Returns:
            DhanResilienceConfig instance with values from dict or defaults.
        """
        if data is None:
            return cls()

        # Extract nested configs
        rate_limit_data = data.get("rate_limit", {})
        retry_data = data.get("retry", {})
        circuit_breaker_data = data.get("circuit_breaker", {})
        token_data = data.get("token", {})

        return cls(
            rate_limit=DhanRateLimitConfig(
                limits=rate_limit_data.get("limits", DEFAULT_RATE_LIMITS.copy()),
                read_prefixes=tuple(rate_limit_data.get("read_prefixes", DEFAULT_READ_CB_PREFIXES)),
                write_prefixes=tuple(rate_limit_data.get("write_prefixes", DEFAULT_WRITE_CB_PREFIXES)),
                bucket_map=rate_limit_data.get("bucket_map", DEFAULT_RL_BUCKET_MAP.copy()),
            ),
            retry=DhanRetryConfig(
                max_retries=retry_data.get("max_retries", DEFAULT_MAX_RETRIES),
                base_delay_ms=retry_data.get("base_delay_ms", DEFAULT_BASE_DELAY_MS),
                max_delay_ms=retry_data.get("max_delay_ms", DEFAULT_MAX_DELAY_MS),
            ),
            circuit_breaker=DhanCircuitBreakerConfig(
                read_prefixes=tuple(circuit_breaker_data.get("read_prefixes", DEFAULT_READ_CB_PREFIXES)),
                write_prefixes=tuple(circuit_breaker_data.get("write_prefixes", DEFAULT_WRITE_CB_PREFIXES)),
                orders_failure_threshold=circuit_breaker_data.get("orders_failure_threshold", 3),
                default_failure_threshold=circuit_breaker_data.get("default_failure_threshold", 5),
                recovery_timeout_ms=circuit_breaker_data.get("recovery_timeout_ms", 30_000),
                success_threshold=circuit_breaker_data.get("success_threshold", 3),
            ),
            token=DhanTokenConfig(
                refresh_cooldown_seconds=token_data.get("refresh_cooldown_seconds", DEFAULT_REFRESH_COOLDOWN_SECONDS),
                rate_limit_backoff_seconds=token_data.get("rate_limit_backoff_seconds", DEFAULT_RATE_LIMIT_BACKOFF_SECONDS),
            ),
            base_url=data.get("base_url", DEFAULT_BASE_URL),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to a dictionary.

        Returns:
            Dictionary representation of all configuration values.
        """
        return {
            "rate_limit": {
                "limits": self.rate_limit.limits,
                "read_prefixes": list(self.rate_limit.read_prefixes),
                "write_prefixes": list(self.rate_limit.write_prefixes),
                "bucket_map": self.rate_limit.bucket_map,
            },
            "retry": {
                "max_retries": self.retry.max_retries,
                "base_delay_ms": self.retry.base_delay_ms,
                "max_delay_ms": self.retry.max_delay_ms,
            },
            "circuit_breaker": {
                "read_prefixes": list(self.circuit_breaker.read_prefixes),
                "write_prefixes": list(self.circuit_breaker.write_prefixes),
                "orders_failure_threshold": self.circuit_breaker.orders_failure_threshold,
                "default_failure_threshold": self.circuit_breaker.default_failure_threshold,
                "recovery_timeout_ms": self.circuit_breaker.recovery_timeout_ms,
                "success_threshold": self.circuit_breaker.success_threshold,
            },
            "token": {
                "refresh_cooldown_seconds": self.token.refresh_cooldown_seconds,
                "rate_limit_backoff_seconds": self.token.rate_limit_backoff_seconds,
            },
            "base_url": self.base_url,
        }


# Default configuration instance
DEFAULT_CONFIG = DhanResilienceConfig()


__all__ = [
    "DhanResilienceConfig",
    "DhanRateLimitConfig",
    "DhanRetryConfig",
    "DhanCircuitBreakerConfig",
    "DhanTokenConfig",
    "DEFAULT_CONFIG",
    "DEFAULT_RATE_LIMITS",
    "DEFAULT_READ_CB_PREFIXES",
    "DEFAULT_WRITE_CB_PREFIXES",
    "DEFAULT_RL_BUCKET_MAP",
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_BASE_DELAY_MS",
    "DEFAULT_MAX_DELAY_MS",
    "DEFAULT_REFRESH_COOLDOWN_SECONDS",
    "DEFAULT_RATE_LIMIT_BACKOFF_SECONDS",
]

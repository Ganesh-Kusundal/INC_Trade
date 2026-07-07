"""Configuration framework.

Provider-agnostic configuration with validation,
environment variable support, and layered overrides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RateLimitConfig:
    """Rate limit configuration for an endpoint category."""

    per_second: int = 10
    per_minute: int = 250
    per_hour: int = 1000
    per_day: int = 7000
    burst: int = 10


@dataclass
class RetryConfig:
    """Retry configuration."""

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass
class StreamConfig:
    """WebSocket streaming configuration."""

    url: str = ""
    reconnect: bool = True
    max_reconnect_attempts: int = 10
    reconnect_delay: float = 1.0
    max_reconnect_delay: float = 60.0
    heartbeat_interval: float = 30.0
    ping_interval: float = 15.0
    message_buffer_size: int = 10000
    dedup_window_ms: int = 500


@dataclass
class CacheConfig:
    """Cache configuration."""

    security_master_ttl: int = 3600  # 1 hour
    quote_ttl: int = 1  # 1 second
    option_chain_ttl: int = 3  # 3 seconds
    instrument_ttl: int = 3600  # 1 hour
    max_size: int = 10000


@dataclass
class ProviderConfig:
    """Provider-specific configuration base."""

    name: str = ""
    base_url: str = ""
    timeout: float = 30.0
    verify_ssl: bool = True
    rate_limits: dict[str, RateLimitConfig] = field(default_factory=dict)
    retry: RetryConfig = field(default_factory=RetryConfig)
    stream: StreamConfig = field(default_factory=StreamConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    extra: dict[str, Any] = field(default_factory=dict)

    def get_rate_limit(self, category: str) -> RateLimitConfig:
        """Get rate limit for a category, with defaults."""
        return self.rate_limits.get(
            category,
            RateLimitConfig(),
        )

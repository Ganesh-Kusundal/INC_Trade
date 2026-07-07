"""Infrastructure layer — cross-cutting resilience, health, logging, and more.

Provides:
    - @rate_limit, @circuit_breaker decorators (resilience)
    - HealthRegistry + @health_check decorator (health)
    - StructuredLogger + get_logger() (structured logging)
    - EventBus (in-process event distribution)
    - MetricsRegistry (counters, gauges, histograms, timers)
    - Tracer (lightweight distributed tracing)
    - Cache / MemoryCache / @cached (caching)
    - TimeService (centralized time)
"""

from brokers.infrastructure.health import HealthEntry, HealthRegistry, HealthStatus, health_check, health_registry
from brokers.infrastructure.logging import StructuredLogger, get_logger
from brokers.infrastructure.resilience import CircuitBreakerOpen, RateLimitExceeded, circuit_breaker, rate_limit
from brokers.infrastructure.event_bus import EventBus, EventHandler
from brokers.infrastructure.metrics import Counter, Gauge, Histogram, MetricsRegistry, Timer, metrics_registry
from brokers.infrastructure.tracing import Span, Tracer, tracer
from brokers.infrastructure.cache import Cache, MemoryCache, async_cached, cached, memory_cache
from brokers.infrastructure.time_service import TimeService, time_service

__all__ = [
    # Resilience
    "CircuitBreakerOpen",
    "RateLimitExceeded",
    "circuit_breaker",
    "rate_limit",
    # Health
    "HealthEntry",
    "HealthRegistry",
    "HealthStatus",
    "health_check",
    "health_registry",
    # Logging
    "StructuredLogger",
    "get_logger",
    # Event bus
    "EventBus",
    "EventHandler",
    # Metrics
    "Counter",
    "Gauge",
    "Histogram",
    "MetricsRegistry",
    "Timer",
    "metrics_registry",
    # Tracing
    "Span",
    "Tracer",
    "tracer",
    # Cache
    "Cache",
    "MemoryCache",
    "async_cached",
    "cached",
    "memory_cache",
    # Time
    "TimeService",
    "time_service",
]

"""Infrastructure protocols — 6 collapsed groups replacing 22 flat interfaces.

The Board rejected the V2 design of 22 separate infrastructure protocols
as "describing frameworks, not behavior." These 6 groups describe WHAT the
system needs, not HOW it's implemented.

Each group maps to a real infrastructure concern:

| Group | Concern | Replaces (V2) |
|-------|---------|---------------|
| HttpPort | HTTP requests | RestClient, RetryEngine, RateLimiter |
| WebSocketPort | Bidirectional streaming | WebSocketClient, ConnectionManager, ReconnectManager, HeartbeatManager, SubscriptionManager |
| SecurityPort | Auth, tokens, secrets | AuthenticationManager, TokenManager, SessionManager, SecretsManager, ConfigurationManager |
| ObservabilityPort | Metrics, logs, traces, health | MetricsCollector, LoggingManager, TracingManager, HealthMonitor |
| DataAccessPort | Caching, persistence | Cache, TokenStorePort |
| ConcurrencyPort | Threads, scheduling, DI | ThreadPoolManager, Scheduler, DIContainer |

All protocols are @runtime_checkable for structural type checking.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable

# ── Group 1: HttpPort ──────────────────────────────────────────────────────────


@runtime_checkable
class HttpPort(Protocol):
    """HTTP client operations — request/response over HTTP.

    Replaces V2's RestClient + RetryEngine + RateLimiter.
    """

    async def request(self, method: str, url: str, **kwargs: Any) -> Any: ...
    async def get(self, url: str, **kwargs: Any) -> Any: ...
    async def post(self, url: str, **kwargs: Any) -> Any: ...
    async def put(self, url: str, **kwargs: Any) -> Any: ...
    async def delete(self, url: str, **kwargs: Any) -> Any: ...


# ── Group 2: WebSocketPort ─────────────────────────────────────────────────────


@runtime_checkable
class WebSocketPort(Protocol):
    """WebSocket connection operations.

    Replaces V2's WebSocketClient + ConnectionManager + ReconnectManager
    + HeartbeatManager + SubscriptionManager.
    """

    async def connect(self, url: str, **kwargs: Any) -> None: ...
    async def disconnect(self) -> None: ...
    async def send(self, message: Any) -> None: ...
    async def receive(self) -> Any: ...

    def subscribe(self, channel: str, handler: Callable[..., Any]) -> Any: ...
    def unsubscribe(self, channel: str) -> None: ...

    @property
    def is_connected(self) -> bool: ...
    @property
    def latency_ms(self) -> float: ...


# ── Group 3: SecurityPort ──────────────────────────────────────────────────────


@runtime_checkable
class SecurityPort(Protocol):
    """Authentication, authorization, and secrets management.

    Replaces V2's AuthenticationManager + TokenManager + SessionManager
    + SecretsManager + ConfigurationManager.
    """

    async def login(self, **credentials: Any) -> Any: ...
    async def logout(self) -> None: ...
    async def refresh_token(self) -> Any: ...
    def get_token(self) -> Any | None: ...
    def is_authenticated(self) -> bool: ...
    def get_secret(self, key: str) -> str | None: ...
    def store_secret(self, key: str, value: str) -> None: ...


# ── Group 4: ObservabilityPort ────────────────────────────────────────────────


@runtime_checkable
class ObservabilityPort(Protocol):
    """Metrics, logging, tracing, and health monitoring.

    Replaces V2's MetricsCollector + LoggingManager + TracingManager
    + HealthMonitor.
    """

    def counter(self, name: str, value: float = 1.0, tags: dict | None = None) -> None: ...
    def gauge(self, name: str, value: float, tags: dict | None = None) -> None: ...
    def histogram(self, name: str, value: float, tags: dict | None = None) -> None: ...
    def start_span(self, name: str, tags: dict | None = None) -> Any: ...
    def end_span(self, span: Any) -> None: ...
    def is_healthy(self) -> bool: ...
    def register_health_check(self, name: str, check: Callable[[], bool]) -> None: ...


# ── Group 5: DataAccessPort ────────────────────────────────────────────────────


@runtime_checkable
class DataAccessPort(Protocol):
    """Caching and state persistence.

    Replaces V2's Cache + TokenStorePort.
    """

    def get(self, key: str) -> Any | None: ...
    def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None: ...
    def invalidate(self, key: str) -> None: ...

    def clear(self) -> None: ...
    def has(self, key: str) -> bool: ...
    def stats(self) -> dict[str, Any]: ...


# ── Group 6: ConcurrencyPort ──────────────────────────────────────────────────


@runtime_checkable
class ConcurrencyPort(Protocol):
    """Thread pools, scheduling, and async execution.

    Replaces V2's ThreadPoolManager + Scheduler + DIContainer.
    DI container is explicitly YAGNI for v1 — manual wiring is sufficient.
    """

    def submit(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any: ...
    def schedule(self, interval_seconds: float, fn: Callable[[], None]) -> Any: ...
    def schedule_once(self, delay_seconds: float, fn: Callable[[], None]) -> Any: ...
    def cancel(self, handle: Any) -> None: ...
    def shutdown(self) -> None: ...


# ── Re-exports for backward compatibility ──────────────────────────────────────

# Old V2 protocol names can still be imported from this module.
# They are type aliases pointing to the new collapsed groups.
AuthPort = SecurityPort
TokenManager = SecurityPort
"""Backward-compatible alias: ``from inc_trade.ports.infrastructure import AuthPort``."""

"""Timeout constants — stop timeouts, HTTP timeouts, sleep intervals, and reconnect delays.

All time-based timeout values used across the broker adapters, lifecycle
management, HTTP clients, and WebSocket reconnection. Centralizing these
prevents magic-number scattering and makes tuning a single-file change.
"""

from __future__ import annotations

# ── Service Timeouts (seconds) ──────────────────────────────────────────────

#: Default ``stop(timeout_seconds=...)`` for any ManagedService.
#: Used by LifecycleManager.drain, HttpObservabilityServer, Dhan depth feeds,
#: and the Dhan connection's ``close()`` call. Five seconds is the value
#: the certification report (M-7) verified empirically; do not change
#: without re-running the chaos tests in ``tests/chaos/``.
DEFAULT_STOP_TIMEOUT_SECONDS: float = 5.0

#: Default HTTP client timeout (Upstox http.py default is 15s).
DEFAULT_HTTP_TIMEOUT_SECONDS: float = 15.0

#: Minimum sleep chunk used by rate-limiter and reconciliation tick (seconds).
MIN_SLEEP_SECONDS: float = 0.001

# ── WebSocket Reconnect Delays (seconds) ────────────────────────────────────

#: Initial delay before the first reconnect attempt after a WebSocket
#: disconnection. Used by ``ReconnectStrategy``, ``WebSocketPool``,
#: ``WebSocketRunner``, and all streaming adapters.
DEFAULT_RECONNECT_DELAY: float = 5.0

#: Maximum delay between reconnect attempts (exponential backoff cap).
#: Used alongside ``DEFAULT_RECONNECT_DELAY`` in all reconnect loops.
DEFAULT_MAX_RECONNECT_DELAY: float = 60.0

# ── Token & Auth Timeouts (seconds) ─────────────────────────────────────────

#: Default token lifetime for broker access tokens (24 hours).
#: Used by ``DhanAuth``, ``TokenManager``, and ``JsonTokenStateStore``.
DEFAULT_TOKEN_LIFETIME_SECONDS: int = 86400

#: Default idempotency cache TTL (1 hour).
#: Used by ``TypedIdempotencyCache`` and ``OrderResultCache``.
DEFAULT_IDEMPOTENCY_TTL_SECONDS: float = 3600.0

__all__ = [
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    "DEFAULT_IDEMPOTENCY_TTL_SECONDS",
    "DEFAULT_MAX_RECONNECT_DELAY",
    "DEFAULT_RECONNECT_DELAY",
    "DEFAULT_STOP_TIMEOUT_SECONDS",
    "DEFAULT_TOKEN_LIFETIME_SECONDS",
    "MIN_SLEEP_SECONDS",
]

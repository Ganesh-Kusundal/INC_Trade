"""Timeout constants — stop timeouts, HTTP timeouts, and sleep intervals.

All time-based timeout values used across the broker adapters, lifecycle
management, and HTTP clients.
"""

from __future__ import annotations

# ── Timeouts (seconds) ─────────────────────────────────────────────────────

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

__all__ = [
    "DEFAULT_HTTP_TIMEOUT_SECONDS",
    "DEFAULT_STOP_TIMEOUT_SECONDS",
    "MIN_SLEEP_SECONDS",
]

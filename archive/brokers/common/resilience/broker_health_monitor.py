"""Broker health monitor — tracks consecutive failures, error rate, and latency.

Provides a thread-safe mechanism to determine whether a broker is healthy
based on consecutive failure counts, recent error rate, and observed latency.
When a broker exceeds the configured failure threshold it is considered
unhealthy until a successful call resets its counter.

Usage::

    monitor = BrokerHealthMonitor(failure_threshold=5)
    monitor.record_success("dhan", latency_ms=120.0)
    monitor.record_failure("upstox")
    if monitor.is_healthy("dhan"):
        ...
    snapshot = monitor.get_health_status()
    print(snapshot["dhan"].error_rate)   # 0.0-1.0
    print(snapshot["dhan"].latency_p50_ms)  # median latency
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass
class BrokerHealthStatus:
    """Point-in-time health snapshot for a single broker."""

    last_successful_call: float | None = None
    consecutive_failures: int = 0
    circuit_state: str = "healthy"  # healthy | unhealthy
    last_health_check: float = 0.0
    error_rate: float = 0.0  # 0.0-1.0 over sliding window
    latency_p50_ms: float = 0.0  # median latency over sliding window
    total_calls: int = 0
    total_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable representation."""
        return {
            "last_successful_call": self.last_successful_call,
            "consecutive_failures": self.consecutive_failures,
            "circuit_state": self.circuit_state,
            "last_health_check": self.last_health_check,
            "error_rate": self.error_rate,
            "latency_p50_ms": self.latency_p50_ms,
            "total_calls": self.total_calls,
            "total_failures": self.total_failures,
        }


@dataclass
class _OutcomeRecord:
    """Single outcome in the sliding window."""

    success: bool
    latency_ms: float
    timestamp: float


class BrokerHealthMonitor:
    """Thread-safe health tracker for one or more brokers.

    Parameters
    ----------
    failure_threshold : int
        Number of consecutive failures after which a broker is
        considered unhealthy. Default is 5.
    window_size : int
        Number of recent outcomes to track for error rate and latency
        computation. Default is 100.
    """

    def __init__(
        self, failure_threshold: int = 5, window_size: int = 100
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError(f"failure_threshold must be positive, got {failure_threshold}")
        self._failure_threshold = failure_threshold
        self._window_size = window_size
        self._lock = threading.RLock()
        # broker_name -> BrokerHealthStatus
        self._health: dict[str, BrokerHealthStatus] = {}
        # broker_name -> deque of _OutcomeRecord
        self._windows: dict[str, deque[_OutcomeRecord]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_success(self, broker: str, latency_ms: float = 0.0) -> None:
        """Record a successful call for *broker*.

        Resets the consecutive-failure counter and marks the broker as
        healthy. Thread-safe.
        """
        now = time.monotonic()
        with self._lock:
            status = self._ensure(broker)
            status.last_successful_call = now
            status.consecutive_failures = 0
            status.circuit_state = "healthy"
            status.last_health_check = now
            status.total_calls += 1
            window = self._ensure_window(broker)
            window.append(_OutcomeRecord(success=True, latency_ms=latency_ms, timestamp=now))
            if len(window) > self._window_size:
                window.popleft()
            self._recompute_stats(broker)

    def record_failure(self, broker: str, latency_ms: float = 0.0) -> None:
        """Record a failed call for *broker*.

        Increments the consecutive-failure counter. If the counter
        reaches the configured threshold the broker transitions to
        ``unhealthy``. Thread-safe.
        """
        now = time.monotonic()
        with self._lock:
            status = self._ensure(broker)
            status.consecutive_failures += 1
            status.last_health_check = now
            status.total_calls += 1
            status.total_failures += 1
            if status.consecutive_failures >= self._failure_threshold:
                status.circuit_state = "unhealthy"
            window = self._ensure_window(broker)
            window.append(_OutcomeRecord(success=False, latency_ms=latency_ms, timestamp=now))
            if len(window) > self._window_size:
                window.popleft()
            self._recompute_stats(broker)

    def is_healthy(self, broker: str) -> bool:
        """Return True if *broker* is considered healthy.

        A broker that has never been seen is treated as healthy
        (optimistic default). Thread-safe.
        """
        with self._lock:
            status = self._health.get(broker)
            if status is None:
                return True  # optimistic: unknown brokers are healthy
            return status.circuit_state == "healthy"

    def get_health_status(self) -> dict[str, BrokerHealthStatus]:
        """Return a snapshot of every broker's health.

        Thread-safe: returns a shallow copy of the inner dicts so
        callers cannot mutate internal state.
        """
        with self._lock:
            return {
                name: BrokerHealthStatus(
                    last_successful_call=s.last_successful_call,
                    consecutive_failures=s.consecutive_failures,
                    circuit_state=s.circuit_state,
                    last_health_check=s.last_health_check,
                    error_rate=s.error_rate,
                    latency_p50_ms=s.latency_p50_ms,
                    total_calls=s.total_calls,
                    total_failures=s.total_failures,
                )
                for name, s in self._health.items()
            }

    def any_healthy(self, brokers: list[str] | None = None) -> bool:
        """Return True if at least one broker in *brokers* is healthy.

        If *brokers* is None, checks every tracked broker. An empty
        list returns False (nothing to check). Thread-safe.
        """
        with self._lock:
            targets = brokers if brokers is not None else list(self._health.keys())
            if not targets:
                return False
            return any(self.is_healthy(b) for b in targets)

    def reset(self, broker: str | None = None) -> None:
        """Reset health tracking.

        If *broker* is given, only that broker is reset. Otherwise
        every tracked broker is cleared. Thread-safe.
        """
        with self._lock:
            if broker is not None:
                self._health.pop(broker, None)
                self._windows.pop(broker, None)
            else:
                self._health.clear()
                self._windows.clear()

    @property
    def failure_threshold(self) -> int:
        return self._failure_threshold

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure(self, broker: str) -> BrokerHealthStatus:
        """Return (and lazily create) the health status for *broker*.

        NOTE: Caller must hold self._lock.
        """
        if broker not in self._health:
            self._health[broker] = BrokerHealthStatus()
        return self._health[broker]

    def _ensure_window(self, broker: str) -> deque[_OutcomeRecord]:
        """Return (and lazily create) the sliding window for *broker*.

        NOTE: Caller must hold self._lock.
        """
        if broker not in self._windows:
            self._windows[broker] = deque(maxlen=self._window_size)
        return self._windows[broker]

    def _recompute_stats(self, broker: str) -> None:
        """Recompute error_rate and latency_p50 from the sliding window.

        NOTE: Caller must hold self._lock.
        """
        status = self._health.get(broker)
        window = self._windows.get(broker)
        if status is None or window is None or not window:
            return

        n = len(window)
        failures = sum(1 for r in window if not r.success)
        status.error_rate = failures / n if n > 0 else 0.0

        latencies = sorted(r.latency_ms for r in window if r.latency_ms > 0)
        if latencies:
            mid = len(latencies) // 2
            if len(latencies) % 2 == 0:
                status.latency_p50_ms = (latencies[mid - 1] + latencies[mid]) / 2
            else:
                status.latency_p50_ms = latencies[mid]
        else:
            status.latency_p50_ms = 0.0

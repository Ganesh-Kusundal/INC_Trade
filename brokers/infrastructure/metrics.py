"""Metrics registry — in-memory counters, gauges, histograms, and timers.

Zero external dependencies. Provides Prometheus-compatible snapshot format.

Usage::

    from brokers.infrastructure.metrics import metrics_registry

    orders_placed = metrics_registry.counter("orders_placed_total", "Orders placed")
    orders_placed.inc()
    orders_placed.inc(5)

    latency = metrics_registry.histogram("order_latency_ms", "Order latency")
    latency.observe(12.5)

    snapshot = metrics_registry.snapshot()
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any


class Counter:
    """Monotonically increasing counter."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._value: float = 0
        self._lock = threading.Lock()

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    @property
    def value(self) -> float:
        with self._lock:
            return self._value

    def reset(self) -> None:
        with self._lock:
            self._value = 0


class Gauge:
    """Metric that can go up and down."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self._value: float = 0
        self._lock = threading.Lock()

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0) -> None:
        with self._lock:
            self._value -= amount

    @property
    def value(self) -> float:
        with self._lock:
            return self._value

    def reset(self) -> None:
        with self._lock:
            self._value = 0


class Histogram:
    """Distribution of observed values with bucket boundaries.

    Uses a bounded ring buffer (max 10,000 observations) to prevent
    unbounded memory growth in long-running processes.
    """

    DEFAULT_BUCKETS = [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0]
    _MAX_VALUES = 10_000

    def __init__(
        self, name: str, description: str = "", buckets: list[float] | None = None
    ) -> None:
        self.name = name
        self.description = description
        self.buckets = sorted(buckets or self.DEFAULT_BUCKETS)
        self.values: deque[float] = deque(maxlen=self._MAX_VALUES)
        self._lock = threading.Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            self.values.append(value)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self.values)

    @property
    def total(self) -> float:
        with self._lock:
            return sum(self.values)

    def bucket_counts(self) -> list[tuple[float, int]]:
        """Return (upper_bound, cumulative_count) pairs."""
        with self._lock:
            sorted_vals = sorted(self.values)
        result: list[tuple[float, int]] = []
        idx = 0
        for bound in self.buckets:
            while idx < len(sorted_vals) and sorted_vals[idx] <= bound:
                idx += 1
            result.append((bound, idx))
        result.append((float("inf"), len(sorted_vals)))
        return result

    def reset(self) -> None:
        with self._lock:
            self.values.clear()


class Timer:
    """Records timing durations in milliseconds.

    Uses a bounded ring buffer (max 10,000 observations) to prevent
    unbounded memory growth in long-running processes.
    """

    _MAX_VALUES = 10_000

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self.values: deque[float] = deque(maxlen=self._MAX_VALUES)
        self._lock = threading.Lock()

    def observe(self, duration_ms: float) -> None:
        with self._lock:
            self.values.append(duration_ms)

    def time(self) -> _TimerContext:
        """Context manager that records elapsed time."""
        return _TimerContext(self)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self.values)

    @property
    def mean(self) -> float:
        with self._lock:
            return sum(self.values) / len(self.values) if self.values else 0.0

    @property
    def p50(self) -> float:
        return self._percentile(50)

    @property
    def p95(self) -> float:
        return self._percentile(95)

    @property
    def p99(self) -> float:
        return self._percentile(99)

    def _percentile(self, pct: float) -> float:
        with self._lock:
            if not self.values:
                return 0.0
            sorted_vals = sorted(self.values)
            idx = int(len(sorted_vals) * pct / 100)
            return sorted_vals[min(idx, len(sorted_vals) - 1)]

    def reset(self) -> None:
        with self._lock:
            self.values.clear()


class _TimerContext:
    """Context manager for Timer.time()."""

    def __init__(self, timer: Timer) -> None:
        self._timer = timer
        self._start: float = 0

    def __enter__(self) -> _TimerContext:
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        elapsed_ms = (time.monotonic() - self._start) * 1000.0
        self._timer.observe(elapsed_ms)


class MetricsRegistry:
    """Central registry for all application metrics."""

    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._timers: dict[str, Timer] = {}
        self._lock = threading.Lock()

    def counter(self, name: str, description: str = "") -> Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, description)
            return self._counters[name]

    def gauge(self, name: str, description: str = "") -> Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, description)
            return self._gauges[name]

    def histogram(self, name: str, description: str = "", buckets: list[float] | None = None) -> Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, description, buckets)
            return self._histograms[name]

    def timer(self, name: str, description: str = "") -> Timer:
        with self._lock:
            if name not in self._timers:
                self._timers[name] = Timer(name, description)
            return self._timers[name]

    def snapshot(self) -> dict[str, Any]:
        """Return a point-in-time snapshot of all metrics."""
        with self._lock:
            return {
                "counters": {n: c.value for n, c in self._counters.items()},
                "gauges": {n: g.value for n, g in self._gauges.items()},
                "histograms": {
                    n: {"count": h.count, "total": h.total}
                    for n, h in self._histograms.items()
                },
                "timers": {
                    n: {"count": t.count, "mean": t.mean, "p95": t.p95}
                    for n, t in self._timers.items()
                },
            }

    def reset_all(self) -> None:
        with self._lock:
            for c in self._counters.values():
                c.reset()
            for g in self._gauges.values():
                g.reset()
            for h in self._histograms.values():
                h.reset()
            for t in self._timers.values():
                t.reset()


# Module-level singleton
metrics_registry = MetricsRegistry()


__all__ = [
    "Counter",
    "Gauge",
    "Histogram",
    "MetricsRegistry",
    "Timer",
    "metrics_registry",
]

"""Metrics collection framework.

Provider-agnostic metrics for monitoring SDK health and performance.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MetricPoint:
    """A single metric data point."""

    name: str
    value: float
    timestamp: float
    tags: dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """In-memory metrics collector.

    Tracks counters, gauges, and histograms.
    Thread-safe for asyncio.
    """

    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._timers: dict[str, list[float]] = defaultdict(list)
        self._points: list[MetricPoint] = []
        self._max_points = 10000

    def increment(self, name: str, value: float = 1.0, **tags: str) -> None:
        """Increment a counter."""
        key = self._make_key(name, tags)
        self._counters[key] += value
        self._record(name, self._counters[key], tags)

    def gauge(self, name: str, value: float, **tags: str) -> None:
        """Set a gauge value."""
        key = self._make_key(name, tags)
        self._gauges[key] = value
        self._record(name, value, tags)

    def histogram(self, name: str, value: float, **tags: str) -> None:
        """Record a histogram value."""
        key = self._make_key(name, tags)
        self._histograms[key].append(value)
        # Keep last 1000 values
        if len(self._histograms[key]) > 1000:
            self._histograms[key] = self._histograms[key][-1000:]
        self._record(name, value, tags)

    def timer(self, name: str, **tags: str) -> _TimerContext:
        """Return a context manager for timing operations."""
        return _TimerContext(self, name, tags)

    def get_counter(self, name: str, **tags: str) -> float:
        """Get current counter value."""
        return self._counters.get(self._make_key(name, tags), 0.0)

    def get_gauge(self, name: str, **tags: str) -> Optional[float]:
        """Get current gauge value."""
        return self._gauges.get(self._make_key(name, tags))

    def get_histogram_stats(self, name: str, **tags: str) -> dict[str, float]:
        """Get histogram statistics."""
        key = self._make_key(name, tags)
        values = self._histograms.get(key, [])
        if not values:
            return {"count": 0, "min": 0, "max": 0, "mean": 0, "p50": 0, "p95": 0, "p99": 0}

        sorted_vals = sorted(values)
        count = len(sorted_vals)
        return {
            "count": count,
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "mean": sum(sorted_vals) / count,
            "p50": sorted_vals[count // 2],
            "p95": sorted_vals[int(count * 0.95)],
            "p99": sorted_vals[int(count * 0.99)],
        }

    def snapshot(self) -> dict[str, Any]:
        """Get a snapshot of all metrics."""
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {k: self.get_histogram_stats(k.split("|")[0]) for k in self._histograms},
        }

    def reset(self) -> None:
        """Reset all metrics."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._timers.clear()
        self._points.clear()

    def _record(self, name: str, value: float, tags: dict[str, str]) -> None:
        point = MetricPoint(name=name, value=value, timestamp=time.time(), tags=tags)
        self._points.append(point)
        if len(self._points) > self._max_points:
            self._points = self._points[-self._max_points :]

    @staticmethod
    def _make_key(name: str, tags: dict[str, str]) -> str:
        if not tags:
            return name
        tag_str = "|".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}|{tag_str}"


class _TimerContext:
    """Context manager for timing operations."""

    def __init__(self, collector: MetricsCollector, name: str, tags: dict[str, str]) -> None:
        self._collector = collector
        self._name = name
        self._tags = tags
        self._start: float = 0

    async def __aenter__(self) -> _TimerContext:
        self._start = time.monotonic()
        return self

    async def __aexit__(self, *args: Any) -> None:
        elapsed = time.monotonic() - self._start
        self._collector.histogram(f"{self._name}.duration_ms", elapsed * 1000, **self._tags)

    def __enter__(self) -> _TimerContext:
        self._start = time.monotonic()
        return self

    def __exit__(self, *args: Any) -> None:
        elapsed = time.monotonic() - self._start
        self._collector.histogram(f"{self._name}.duration_ms", elapsed * 1000, **self._tags)

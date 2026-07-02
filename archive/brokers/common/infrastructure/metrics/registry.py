"""Metrics registry for centralized metric management."""
from __future__ import annotations

from threading import Lock
from typing import Any

from infrastructure.metrics.types import (
    Counter,
    Gauge,
    Histogram,
    LabelledCounter,
    LabelledGauge,
    LabelledHistogram,
    Timer,
)


class MetricsRegistry:
    """Central registry for all application metrics."""

    def __init__(self) -> None:
        self._counters: dict[str, Counter] = {}
        self._gauges: dict[str, Gauge] = {}
        self._histograms: dict[str, Histogram] = {}
        self._timers: dict[str, Timer] = {}
        self._labelled_counters: dict[str, LabelledCounter] = {}
        self._labelled_gauges: dict[str, LabelledGauge] = {}
        self._labelled_histograms: dict[str, LabelledHistogram] = {}
        self._lock = Lock()

    def counter(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> Counter:
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, description, labels)
            return self._counters[name]

    def gauge(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> Gauge:
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, description, labels)
            return self._gauges[name]

    def histogram(self, name: str, description: str = "", labels: dict[str, str] | None = None, buckets: list[float] | None = None) -> Histogram:
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, description, labels, buckets)
            return self._histograms[name]

    def timer(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> Timer:
        with self._lock:
            if name not in self._timers:
                self._timers[name] = Timer(name, description, labels)
            return self._timers[name]

    def labelled_counter(
        self, name: str, description: str = "", label_names: tuple[str, ...] = ()
    ) -> LabelledCounter:
        with self._lock:
            if name not in self._labelled_counters:
                self._labelled_counters[name] = LabelledCounter(name, description, label_names)
            return self._labelled_counters[name]

    def labelled_gauge(
        self, name: str, description: str = "", label_names: tuple[str, ...] = ()
    ) -> LabelledGauge:
        with self._lock:
            if name not in self._labelled_gauges:
                self._labelled_gauges[name] = LabelledGauge(name, description, label_names)
            return self._labelled_gauges[name]

    def labelled_histogram(
        self,
        name: str,
        description: str = "",
        label_names: tuple[str, ...] = (),
        buckets: list[float] | None = None,
    ) -> LabelledHistogram:
        with self._lock:
            if name not in self._labelled_histograms:
                self._labelled_histograms[name] = LabelledHistogram(
                    name, description, label_names, buckets
                )
            return self._labelled_histograms[name]

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": {n: c.value for n, c in self._counters.items()},
                "gauges": {n: g.value for n, g in self._gauges.items()},
                "histograms": {n: len(h.values) for n, h in self._histograms.items()},
                "timers": {n: len(t.values) for n, t in self._timers.items()},
                "labelled_counters": {
                    n: {str(k): v for k, v in c.snapshot().items()}
                    for n, c in self._labelled_counters.items()
                },
                "labelled_gauges": {
                    n: {str(k): v for k, v in g.snapshot().items()}
                    for n, g in self._labelled_gauges.items()
                },
                "labelled_histograms": {
                    n: {str(k): len(v) for k, v in h.snapshot().items()}
                    for n, h in self._labelled_histograms.items()
                },
            }

    @staticmethod
    def _compute_buckets(values: list[float], buckets: list[float]) -> list[tuple[float, int]]:
        sorted_buckets = sorted(buckets)
        result: list[tuple[float, int]] = []
        cumulative = 0
        for bound in sorted_buckets:
            cumulative = sum(1 for v in values if v <= bound)
            result.append((bound, cumulative))
        result.append((float("inf"), len(values)))
        return result

    def snapshot_detailed(self) -> dict[str, Any]:
        """Full snapshot with bucket distributions and timer stats for Prometheus export."""
        with self._lock:
            histograms = {}
            for n, h in self._histograms.items():
                values = h.values
                bucket_counts = self._compute_buckets(values, h.buckets)
                histograms[n] = {
                    "description": h.description,
                    "labels": h.labels,
                    "buckets": bucket_counts,
                    "sum": sum(values),
                    "count": len(values),
                }

            timers = {}
            for n, t in self._timers.items():
                values = t.values
                timers[n] = {
                    "description": t.description,
                    "labels": t.labels,
                    "count": len(values),
                    "sum": sum(values),
                    "min": min(values) if values else 0,
                    "max": max(values) if values else 0,
                    "avg": sum(values) / len(values) if values else 0,
                }

            labelled_histograms = {}
            for n, h in self._labelled_histograms.items():
                series_data = {}
                for key, values in h.snapshot().items():
                    bucket_counts = self._compute_buckets(values, h.buckets)
                    series_data[str(key)] = {
                        "buckets": bucket_counts,
                        "sum": sum(values),
                        "count": len(values),
                    }
                labelled_histograms[n] = {
                    "description": h.description,
                    "label_names": h.label_names,
                    "series": series_data,
                }

            return {
                "counters": {
                    n: {"value": c.value, "description": c.description, "labels": c.labels}
                    for n, c in self._counters.items()
                },
                "gauges": {
                    n: {"value": g.value, "description": g.description, "labels": g.labels}
                    for n, g in self._gauges.items()
                },
                "histograms": histograms,
                "timers": timers,
                "labelled_counters": {
                    n: {
                        "description": c.description,
                        "label_names": c.label_names,
                        "series": {str(k): v for k, v in c.snapshot().items()},
                    }
                    for n, c in self._labelled_counters.items()
                },
                "labelled_gauges": {
                    n: {
                        "description": g.description,
                        "label_names": g.label_names,
                        "series": {str(k): v for k, v in g.snapshot().items()},
                    }
                    for n, g in self._labelled_gauges.items()
                },
                "labelled_histograms": labelled_histograms,
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
            for c in self._labelled_counters.values():
                c.reset()
            for g in self._labelled_gauges.values():
                g.reset()
            for h in self._labelled_histograms.values():
                h.reset()


metrics_registry = MetricsRegistry()

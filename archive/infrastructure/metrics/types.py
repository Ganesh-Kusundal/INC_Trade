"""Metric type definitions for the metrics system."""
from __future__ import annotations

import random
import time
from collections.abc import Generator
from contextlib import contextmanager
from threading import Lock


class Counter:
    """Monotonically increasing counter metric."""

    def __init__(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> None:
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._value: float = 0
        self._lock = Lock()

    def inc(self, value: float = 1.0) -> None:
        if value < 0:
            raise ValueError(f"Counter.inc() requires non-negative value, got {value}")
        with self._lock:
            self._value += value

    def reset(self) -> None:
        with self._lock:
            self._value = 0

    @property
    def value(self) -> float:
        with self._lock:
            return self._value


class Gauge:
    """Up/down gauge metric."""

    def __init__(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> None:
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._value: float = 0
        self._lock = Lock()

    def set(self, value: float) -> None:
        with self._lock:
            self._value = value

    def inc(self, value: float = 1.0) -> None:
        with self._lock:
            self._value += value

    def dec(self, value: float = 1.0) -> None:
        with self._lock:
            self._value -= value

    def reset(self) -> None:
        with self._lock:
            self._value = 0

    @property
    def value(self) -> float:
        with self._lock:
            return self._value



class Histogram:
    """Histogram metric for measuring distributions."""

    _MAX_SAMPLES = 10_000

    def __init__(self, name: str, description: str = "", labels: dict[str, str] | None = None, buckets: list[float] | None = None) -> None:
        self.name = name
        self.description = description
        self.labels = labels or {}
        self.buckets = buckets or [.005, .01, .025, .05, .1, .25, .5, 1, 2.5, 5, 10]
        self._values: list[float] = []
        self._count: int = 0
        self._lock = Lock()

    def observe(self, value: float) -> None:
        with self._lock:
            self._count += 1
            if len(self._values) < self._MAX_SAMPLES:
                self._values.append(value)
            else:
                idx = random.randint(0, self._count - 1)  # noqa: S311
                if idx < self._MAX_SAMPLES:
                    self._values[idx] = value

    @contextmanager
    def time(self) -> Generator[None, None, None]:
        start = time.monotonic()
        try:
            yield
        finally:
            self.observe(time.monotonic() - start)

    @property
    def values(self) -> list[float]:
        with self._lock:
            return list(self._values)

    def reset(self) -> None:
        with self._lock:
            self._values.clear()
            self._count = 0


class Timer:
    """Timer metric for measuring operation duration."""

    _MAX_SAMPLES = 10_000

    def __init__(self, name: str, description: str = "", labels: dict[str, str] | None = None) -> None:
        self.name = name
        self.description = description
        self.labels = labels or {}
        self._values: list[float] = []
        self._count: int = 0
        self._lock = Lock()

    @contextmanager
    def time(self) -> Generator[None, None, None]:
        start = time.monotonic()
        try:
            yield
        finally:
            self.observe(time.monotonic() - start)

    def observe(self, value: float) -> None:
        with self._lock:
            self._count += 1
            if len(self._values) < self._MAX_SAMPLES:
                self._values.append(value)
            else:
                idx = random.randint(0, self._count - 1)  # noqa: S311
                if idx < self._MAX_SAMPLES:
                    self._values[idx] = value

    @property
    def values(self) -> list[float]:
        with self._lock:
            return list(self._values)

    def reset(self) -> None:
        with self._lock:
            self._values.clear()
            self._count = 0


class LabelledCounter:
    """Counter with dynamic label combinations (multiple time series).

    Unlike Counter which has fixed labels, LabelledCounter supports
    recording values with different label combinations at runtime.
    Example: HTTP requests with varying method/path/status labels.
    """

    def __init__(self, name: str, description: str = "", label_names: tuple[str, ...] = ()) -> None:
        self.name = name
        self.description = description
        self.label_names = label_names
        self._series: dict[tuple[str, ...], float] = {}
        self._lock = Lock()

    def inc(self, value: float = 1.0, **labels: str) -> None:
        if value < 0:
            raise ValueError(f"Counter.inc() requires non-negative value, got {value}")
        key = tuple(labels.get(name, "") for name in self.label_names)
        with self._lock:
            self._series[key] = self._series.get(key, 0.0) + value

    def get(self, **labels: str) -> float:
        key = tuple(labels.get(name, "") for name in self.label_names)
        with self._lock:
            return self._series.get(key, 0.0)

    def snapshot(self) -> dict[tuple[str, ...], float]:
        with self._lock:
            return dict(self._series)

    def reset(self) -> None:
        with self._lock:
            self._series.clear()


class LabelledGauge:
    """Gauge with dynamic label combinations (multiple time series).

    Unlike Gauge which has fixed labels, LabelledGauge supports
    setting values with different label combinations at runtime.
    """

    def __init__(self, name: str, description: str = "", label_names: tuple[str, ...] = ()) -> None:
        self.name = name
        self.description = description
        self.label_names = label_names
        self._series: dict[tuple[str, ...], float] = {}
        self._lock = Lock()

    def set(self, value: float, **labels: str) -> None:
        key = tuple(labels.get(name, "") for name in self.label_names)
        with self._lock:
            self._series[key] = value

    def inc(self, value: float = 1.0, **labels: str) -> None:
        key = tuple(labels.get(name, "") for name in self.label_names)
        with self._lock:
            self._series[key] = self._series.get(key, 0.0) + value

    def dec(self, value: float = 1.0, **labels: str) -> None:
        key = tuple(labels.get(name, "") for name in self.label_names)
        with self._lock:
            self._series[key] = self._series.get(key, 0.0) - value

    def get(self, **labels: str) -> float:
        key = tuple(labels.get(name, "") for name in self.label_names)
        with self._lock:
            return self._series.get(key, 0.0)

    def snapshot(self) -> dict[tuple[str, ...], float]:
        with self._lock:
            return dict(self._series)

    def reset(self) -> None:
        with self._lock:
            self._series.clear()


class LabelledHistogram:
    """Histogram with dynamic label combinations (multiple time series).

    Supports recording observations with different label combinations.
    Each label combination maintains its own set of observations.
    """

    _MAX_SAMPLES = 10_000

    def __init__(
        self,
        name: str,
        description: str = "",
        label_names: tuple[str, ...] = (),
        buckets: list[float] | None = None,
    ) -> None:
        self.name = name
        self.description = description
        self.label_names = label_names
        self.buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        self._series: dict[tuple[str, ...], list[float]] = {}
        self._counts: dict[tuple[str, ...], int] = {}
        self._lock = Lock()

    def observe(self, value: float, **labels: str) -> None:
        key = tuple(labels.get(name, "") for name in self.label_names)
        with self._lock:
            self._counts[key] = self._counts.get(key, 0) + 1
            if key not in self._series:
                self._series[key] = []
            if len(self._series[key]) < self._MAX_SAMPLES:
                self._series[key].append(value)
            else:
                idx = random.randint(0, self._counts[key] - 1)  # noqa: S311
                if idx < self._MAX_SAMPLES:
                    self._series[key][idx] = value

    def snapshot(self) -> dict[tuple[str, ...], list[float]]:
        with self._lock:
            return {k: list(v) for k, v in self._series.items()}

    def reset(self) -> None:
        with self._lock:
            self._series.clear()
            self._counts.clear()

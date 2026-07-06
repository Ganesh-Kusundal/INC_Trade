"""In-process event metrics for the OMS / event bus.

Thread-safe counter store keyed by ``(event_type, outcome)`` with support
for both simple cumulative counters and timestamped rate-based counters.

The metrics here are **never** swallowed. Every increment is observable
via :func:`snapshot`, which is what the alerting layer polls.

Prometheus Exposition
---------------------
The :meth:`EventMetrics.prometheus_exposition` method renders all counters
in the Prometheus text exposition format, suitable for scraping by a
Prometheus server or compatible collector.

Usage::

    from brokers_core.infrastructure.observability.event_metrics import EventMetrics

    metrics = EventMetrics()
    metrics.inc("ORDER", "published")
    metrics.add_timestamped_counter("TICK", "handler_error", time.time())
    print(metrics.prometheus_exposition())
"""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from threading import Lock
from typing import Any

# ---------------------------------------------------------------------------
# Self-contained Counter (avoids dependency on infrastructure.metrics)
# ---------------------------------------------------------------------------


class _Counter:
    """Monotonically increasing counter metric.

    Self-contained implementation to avoid coupling with the metrics
    registry module. Thread-safe via internal lock.
    """

    def __init__(
        self,
        name: str,
        description: str = "",
        labels: dict[str, str] | None = None,
    ) -> None:
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


# ---------------------------------------------------------------------------
# Timestamped counter entry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TimestampedCounter:
    """A single metric event with a wall-clock timestamp.

    Used by :meth:`add_timestamped_counter` to enable rate-based
    alerting (e.g., "more than 10 errors in the last 60 seconds").
    """

    event_type: str
    outcome: str
    timestamp: float
    by: int = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COUNTER_PREFIX = "event_metrics__"


def _sanitize_name(name: str) -> str:
    """Sanitize a string for use as a metric counter name."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def _escape_label_value(value: str) -> str:
    """Escape a label value for Prometheus exposition format.

    Backslashes, double-quotes, and newlines must be escaped per the
    Prometheus text format specification.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _format_labels(labels: dict[str, str]) -> str:
    """Format a label set for Prometheus exposition: ``{key="value",...}``."""
    if not labels:
        return ""
    parts = [
        f'{k}="{_escape_label_value(v)}"'
        for k, v in sorted(labels.items())
    ]
    return "{" + ",".join(parts) + "}"


# ---------------------------------------------------------------------------
# EventMetrics
# ---------------------------------------------------------------------------


class EventMetrics:
    """Thread-safe counter store keyed by ``(event_type, outcome)``.

    Outcomes used by the bus:

    - ``published`` -- event was accepted by the bus.
    - ``dispatched`` -- handler invocation started.
    - ``handler_ok`` -- handler returned without raising.
    - ``handler_error`` -- handler raised (counted per (event_type, error_type)).
    - ``dead_letter`` -- handler failures sent to the dead-letter queue.
    - ``log_error`` -- persistent log append failed (counted per error type).
    - ``duplicated_trade`` -- a trade that was already processed (idempotency hit).

    Rate-Based Alerting
    -------------------
    In addition to simple counters, this class supports timestamped
    counters via :meth:`add_timestamped_counter` and :meth:`rate`.
    These enable alerting rules like "error rate > 5% in the last 60s".

    All timestamped entries are pruned automatically when the rate
    is calculated to prevent unbounded memory growth.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._counters: dict[tuple[str, str], _Counter] = {}
        self._timestamped: dict[tuple[str, str], list[tuple[float, int]]] = defaultdict(list)

    @staticmethod
    def _counter_name(event_type: str, outcome: str) -> str:
        return f"{_COUNTER_PREFIX}{_sanitize_name(event_type)}__{_sanitize_name(outcome)}"

    def _get_or_create_counter(self, event_type: str, outcome: str) -> _Counter:
        key = (event_type, outcome)
        counter = self._counters.get(key)
        if counter is not None:
            return counter
        with self._lock:
            counter = self._counters.get(key)
            if counter is None:
                name = self._counter_name(event_type, outcome)
                counter = _Counter(
                    name,
                    description=f"Event counter for {event_type}/{outcome}",
                    labels={"event_type": event_type, "outcome": outcome},
                )
                self._counters[key] = counter
            return counter

    def inc(self, event_type: str, outcome: str, by: int = 1) -> None:
        """Increment a counter by *by* (must be positive).

        This is the original API -- it remains backward compatible.
        For rate-based alerting, prefer :meth:`add_timestamped_counter`.
        """
        if by <= 0:
            return
        counter = self._get_or_create_counter(event_type, outcome)
        counter.inc(by)

    def add_timestamped_counter(
        self,
        event_type: str,
        outcome: str,
        timestamp: float | None = None,
        by: int = 1,
    ) -> None:
        """Record a metric event with a wall-clock timestamp.

        This stores the event in both the simple counter (for backward
        compatibility) and a timestamped log (for rate calculation).

        Parameters
        ----------
        event_type:
            The event type (e.g., "TICK", "ORDER_PLACED").
        outcome:
            The outcome (e.g., "published", "handler_error:RuntimeError").
        timestamp:
            Unix timestamp. Defaults to :func:`time.time` if omitted.
        by:
            Increment amount (must be positive).
        """
        if by <= 0:
            return
        ts = timestamp if timestamp is not None else time.time()
        counter = self._get_or_create_counter(event_type, outcome)
        counter.inc(by)
        self._timestamped[(event_type, outcome)].append((ts, by))

    def rate(
        self,
        event_type: str,
        outcome: str,
        window_seconds: float,
    ) -> float:
        """Calculate the rate (events per second) over a recent time window.

        This looks at timestamped counters recorded via
        :meth:`add_timestamped_counter` and computes how many events
        occurred in the last *window_seconds*.

        Parameters
        ----------
        event_type:
            The event type to query.
        outcome:
            The outcome to query.
        window_seconds:
            Lookback window in seconds (e.g., 60.0 for "last 60 seconds").

        Returns
        -------
        float:
            Events per second over the window. Returns 0.0 if no events
            were recorded or the window is invalid.

        Example
        -------
        >>> metrics = EventMetrics()
        >>> metrics.add_timestamped_counter("TICK", "handler_error", time.time())
        >>> metrics.rate("TICK", "handler_error", window_seconds=60.0)
        0.016666...  # 1 event / 60 seconds
        """
        if window_seconds <= 0:
            return 0.0

        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            entries = self._timestamped.get((event_type, outcome), [])
            if not entries:
                return 0.0

            recent_entries: list[tuple[float, int]] = []
            total_count = 0
            for ts, count in entries:
                if ts >= cutoff:
                    recent_entries.append((ts, count))
                    total_count += count

            self._timestamped[(event_type, outcome)] = recent_entries

            if total_count == 0:
                return 0.0

            return total_count / window_seconds

    def get(self, event_type: str, outcome: str) -> int:
        """Return the cumulative counter value for ``(event_type, outcome)``."""
        counter = self._counters.get((event_type, outcome))
        return int(counter.value) if counter else 0

    def snapshot(self) -> dict[str, dict[str, int]]:
        """Return a JSON-serializable view of every counter."""
        with self._lock:
            out: dict[str, dict[str, int]] = defaultdict(dict)
            for (event_type, outcome), counter in self._counters.items():
                out[event_type][outcome] = int(counter.value)
            return dict(out)

    def reset(self) -> None:
        """Clear all counters and timestamped entries."""
        with self._lock:
            for counter in self._counters.values():
                counter.reset()
            self._counters.clear()
            self._timestamped.clear()

    def render(self) -> str:
        """Human-readable rendering, mostly for the CLI / logs."""
        lines = ["event_type | outcome | count"]
        for (event_type, outcome), counter in sorted(self._counters.items()):
            lines.append(f"{event_type} | {outcome} | {int(counter.value)}")
        return "\n".join(lines)

    def as_dict(self) -> dict[str, Any]:
        """Return a dictionary representation suitable for serialization."""
        return {"events": self.snapshot()}

    # ------------------------------------------------------------------
    # Prometheus exposition format
    # ------------------------------------------------------------------

    def prometheus_exposition(self) -> str:
        """Render all counters in Prometheus text exposition format.

        Returns a string conforming to the Prometheus text format
        specification. Each counter is rendered as a single line with
        the metric name, labels, and current value.

        The metric name is derived from the counter name (with the
        internal prefix stripped) and sanitized for Prometheus
        compatibility.

        Example output::

            # HELP event_metrics_ORDER_published Event counter for ORDER/published
            # TYPE event_metrics_ORDER_published counter
            event_metrics_ORDER_published{event_type="ORDER",outcome="published"} 42

        Returns
        -------
        str:
            Prometheus exposition format text.
        """
        lines: list[str] = []
        seen_help: set[str] = set()

        with self._lock:
            for (event_type, outcome), counter in sorted(self._counters.items()):
                metric_name = counter.name
                labels = counter.labels

                # Emit HELP and TYPE exactly once per metric name
                if metric_name not in seen_help:
                    seen_help.add(metric_name)
                    desc = counter.description or metric_name
                    lines.append(f"# HELP {metric_name} {desc}")
                    lines.append(f"# TYPE {metric_name} counter")

                label_str = _format_labels(labels)
                lines.append(f"{metric_name}{label_str} {int(counter.value)}")

        return "\n".join(lines) + "\n" if lines else ""


__all__ = [
    "EventMetrics",
    "TimestampedCounter",
]

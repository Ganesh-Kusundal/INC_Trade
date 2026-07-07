"""Lightweight distributed tracing — context propagation and span recording.

Zero external dependencies. Provides trace/span IDs and a context-local
stack for correlating operations across async boundaries.

Usage::

    from brokers.infrastructure.tracing import tracer

    with tracer.span("place_order", broker="dhan") as span:
        span.set_tag("symbol", "RELIANCE")
        response = await adapter.place_order(request)
        span.set_tag("order_id", response.order_id)
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

# Span stack is per-async-context (not per-thread) so nesting/parenting is
# correct under asyncio, where many coroutines share one thread.  A
# ContextVar provides the right isolation: each task gets its own stack,
# and parent/child spans nest correctly across awaits.
_SPAN_STACK: ContextVar[list[Span]] = ContextVar("tracing_span_stack")

# Bound buffer of finished spans to prevent unbounded memory growth.
_MAX_FINISHED_SPANS = 10_000


@dataclass
class Span:
    """A single trace span — records timing, tags, and errors."""

    name: str
    trace_id: str
    span_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    parent_span_id: str | None = None
    start_time: float = field(default_factory=time.monotonic)
    end_time: float | None = None
    tags: dict[str, Any] = field(default_factory=dict)
    status: str = "OK"
    error: str | None = None

    def set_tag(self, key: str, value: Any) -> None:
        """Set a key-value tag on this span."""
        self.tags[key] = value

    def set_error(self, message: str) -> None:
        """Mark this span as an error."""
        self.status = "ERROR"
        self.error = message

    def finish(self) -> None:
        """Mark the span as finished."""
        self.end_time = time.monotonic()

    @property
    def duration_ms(self) -> float | None:
        """Elapsed time in milliseconds, or None if not yet finished."""
        if self.end_time is None:
            return None
        return (self.end_time - self.start_time) * 1000.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize span to a dictionary."""
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "error": self.error,
            "tags": dict(self.tags),
        }


class Tracer:
    """Lightweight tracer for recording spans and propagating trace context.

    Thread-safe. Each thread maintains its own span stack.
    """

    def __init__(self) -> None:
        self._finished_spans: deque[Span] = deque(maxlen=_MAX_FINISHED_SPANS)
        self._lock = threading.Lock()

    @contextmanager
    def span(
        self, name: str, trace_id: str | None = None, **tags: Any
    ) -> Any:
        """Context manager that creates and manages a span.

        Usage::

            with tracer.span("operation", broker="dhan") as span:
                span.set_tag("key", "value")
        """
        parent = self._current_span()
        span = Span(
            name=name,
            trace_id=trace_id or (parent.trace_id if parent else uuid.uuid4().hex),
            parent_span_id=parent.span_id if parent else None,
            tags=tags,
        )
        self._push_span(span)
        try:
            yield span
            span.finish()
        except Exception as exc:
            span.set_error(str(exc))
            span.finish()
            raise
        finally:
            self._pop_span()
            with self._lock:
                self._finished_spans.append(span)

    def _current_span(self) -> Span | None:
        """Get the current active span from the context-local stack."""
        stack = _SPAN_STACK.get(None)
        return stack[-1] if stack else None

    def _push_span(self, span: Span) -> None:
        stack = _SPAN_STACK.get(None)
        if stack is None:
            stack = []
            _SPAN_STACK.set(stack)
        stack.append(span)

    def _pop_span(self) -> Span | None:
        stack = _SPAN_STACK.get(None)
        if stack:
            return stack.pop()
        return None

    def finished_spans(self) -> list[Span]:
        """Return all finished spans (for export / diagnostics)."""
        with self._lock:
            return list(self._finished_spans)

    def clear_finished(self) -> None:
        """Clear finished spans (useful in tests)."""
        with self._lock:
            self._finished_spans.clear()

    def trace_id(self) -> str | None:
        """Return the current trace ID, or None if no active span."""
        span = self._current_span()
        return span.trace_id if span else None


# Module-level singleton
tracer = Tracer()


__all__ = ["Span", "Tracer", "tracer"]

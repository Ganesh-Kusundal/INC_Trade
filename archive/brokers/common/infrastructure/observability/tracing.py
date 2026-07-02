"""Tracing decorators for critical path observability.

Automatic tracing for order lifecycle, trade execution,
and event handling with correlation ID propagation, duration tracking, and error capture.

When OpenTelemetry is installed and initialised via ``setup_telemetry()``, each
decorated function automatically creates a child span so the call appears in
distributed traces (Jaeger, Zipkin, etc.).  When OTel is unavailable the
decorators fall back to log-only tracing.

Usage:
    from infrastructure.observability.tracing import trace_operation

    @trace_operation("order_placement")
    def place_order(request: OrderRequest) -> OrderResponse:
        # Implementation
        pass

    # Automatically logs:
    # - Start/end with correlation_id
    # - Duration in milliseconds
    # - Success/failure status
    # - Exception details (if any)
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from typing import Any, TypeVar

from infrastructure.correlation import get_current_correlation_id
from infrastructure.logging_config import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# ---------------------------------------------------------------------------
# Optional OpenTelemetry imports — used only when the SDK is available.
# ---------------------------------------------------------------------------

try:
    from opentelemetry import trace as _otel_trace

    _HAS_OTEL = True
except ImportError:
    _otel_trace = None  # type: ignore[assignment]
    _HAS_OTEL = False

try:
    from infrastructure.observability.opentelemetry_setup import otel_available as _otel_active
except ImportError:
    _otel_active = False  # type: ignore[assignment]


def _get_tracer() -> Any:
    """Return the global OTel tracer, or *None* when OTel is unavailable."""
    if _HAS_OTEL and _otel_active:
        return _otel_trace.get_tracer("tradex.tracing")
    return None


def trace_operation(operation_name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator that traces function execution with timing and correlation ID.

    When OpenTelemetry is active a child span is created for each invocation,
    with ``correlation_id``, ``function`` and ``status`` recorded as span
    attributes.

    Args:
        operation_name: Human-readable name for the operation (e.g., "order_placement")

    Returns:
        Decorated function with automatic tracing

    Example:
        @trace_operation("order_placement")
        def place_order(symbol: str, quantity: int) -> Order:
            return Order(...)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            correlation_id = get_current_correlation_id() or "no-correlation"
            start_time = time.perf_counter()

            logger.debug(
                f"Operation started: {operation_name}",
                extra={
                    "operation": operation_name,
                    "function": func.__name__,
                    "correlation_id": correlation_id,
                },
            )

            tracer = _get_tracer()
            if tracer is not None:
                with tracer.start_as_current_span(operation_name) as span:
                    span.set_attribute("correlation_id", correlation_id)
                    span.set_attribute("function", func.__name__)
                    return _execute_traced(span, func, args, kwargs, operation_name, correlation_id, start_time)
            return _execute_traced(None, func, args, kwargs, operation_name, correlation_id, start_time)

        return wrapper

    return decorator


def trace_event_handler(event_type: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator for event bus handlers with automatic tracing.

    When OpenTelemetry is active a child span is created for each invocation,
    with ``event_type`` and ``correlation_id`` recorded as span attributes.

    Args:
        event_type: The event type being handled (e.g., "ORDER_UPDATED")

    Returns:
        Decorated event handler

    Example:
        @trace_event_handler("ORDER_UPDATED")
        def on_order_update(self, event: DomainEvent) -> None:
            # Handle event
            pass
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            correlation_id = get_current_correlation_id() or "no-correlation"
            start_time = time.perf_counter()

            logger.debug(
                f"Event handler started: {event_type}",
                extra={
                    "event_type": event_type,
                    "handler": func.__name__,
                    "correlation_id": correlation_id,
                },
            )

            tracer = _get_tracer()
            span_name = f"event_handler.{event_type}"
            if tracer is not None:
                with tracer.start_as_current_span(span_name) as span:
                    span.set_attribute("event_type", event_type)
                    span.set_attribute("correlation_id", correlation_id)
                    span.set_attribute("function", func.__name__)
                    return _execute_traced(span, func, args, kwargs, event_type, correlation_id, start_time)
            return _execute_traced(None, func, args, kwargs, event_type, correlation_id, start_time)

        return wrapper

    return decorator


def _execute_traced(
    span: Any,
    func: Callable[..., T],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    operation_name: str,
    correlation_id: str,
    start_time: float,
) -> T:
    """Shared helper that executes *func*, records logs/span status, and re-raises."""
    try:
        result = func(*args, **kwargs)
        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.debug(
            f"Operation completed: {operation_name}",
            extra={
                "operation": operation_name,
                "function": func.__name__,
                "duration_ms": round(duration_ms, 2),
                "status": "success",
                "correlation_id": correlation_id,
            },
        )

        if span is not None:
            span.set_attribute("duration_ms", round(duration_ms, 2))
            span.set_attribute("status", "success")

        return result

    except Exception as exc:
        duration_ms = (time.perf_counter() - start_time) * 1000

        logger.error(
            f"Operation failed: {operation_name}",
            extra={
                "operation": operation_name,
                "function": func.__name__,
                "duration_ms": round(duration_ms, 2),
                "status": "error",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "correlation_id": correlation_id,
            },
            exc_info=True,
        )

        if span is not None:
            span.set_attribute("duration_ms", round(duration_ms, 2))
            span.set_attribute("status", "error")
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.record_exception(exc)

        raise


class TraceContext:
    """Context manager for tracing code blocks without decorators.

    Useful for tracing async code or sections where decorators can't be used.

    Example:
        with TraceContext("position_update", symbol="RELIANCE"):
            position.apply_trade(trade)
    """

    def __init__(self, operation_name: str, **extra_context: Any) -> None:
        self.operation_name = operation_name
        self.extra_context = extra_context
        self.correlation_id = get_current_correlation_id() or "no-correlation"
        self.start_time: float = 0

    def __enter__(self) -> TraceContext:
        self.start_time = time.perf_counter()

        logger.debug(
            f"Trace block started: {self.operation_name}",
            extra={
                "operation": self.operation_name,
                "correlation_id": self.correlation_id,
                **self.extra_context,
            },
        )

        return self

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
        duration_ms = (time.perf_counter() - self.start_time) * 1000

        if exc_type is not None:
            logger.error(
                f"Trace block failed: {self.operation_name}",
                extra={
                    "operation": self.operation_name,
                    "duration_ms": round(duration_ms, 2),
                    "status": "error",
                    "error_type": exc_type.__name__,
                    "error_message": str(exc_value),
                    "correlation_id": self.correlation_id,
                    **self.extra_context,
                },
                exc_info=(exc_type, exc_value, traceback),
            )
        else:
            logger.debug(
                f"Trace block completed: {self.operation_name}",
                extra={
                    "operation": self.operation_name,
                    "duration_ms": round(duration_ms, 2),
                    "status": "success",
                    "correlation_id": self.correlation_id,
                    **self.extra_context,
                },
            )


__all__ = [
    "TraceContext",
    "trace_event_handler",
    "trace_operation",
]

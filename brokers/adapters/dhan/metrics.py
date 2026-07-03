"""Dhan API Metrics for Prometheus."""

from __future__ import annotations

import logging
from functools import wraps
from time import perf_counter
from typing import Any, Callable

from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

# Prometheus metrics
DHAN_REQUESTS_TOTAL = Counter(
    "dhan_requests_total", "Total Dhan API requests", ["method", "path", "status"]
)

DHAN_REQUEST_ERRORS = Counter(
    "dhan_request_errors_total",
    "Total Dhan API errors",
    ["method", "path", "error_type"],
)

DHAN_REQUEST_DURATION = Histogram(
    "dhan_request_duration_seconds", "Duration of Dhan API requests", ["method", "path"]
)


class MetricsRegistry:
    """Registry for Prometheus metrics."""

    @staticmethod
    def inc_request(method: str, path: str, status: int | str) -> None:
        DHAN_REQUESTS_TOTAL.labels(method=method, path=path, status=str(status)).inc()

    @staticmethod
    def inc_error(method: str, path: str, error_type: str) -> None:
        DHAN_REQUEST_ERRORS.labels(
            method=method, path=path, error_type=error_type
        ).inc()

    @staticmethod
    def observe_duration(method: str, path: str, duration: float) -> None:
        DHAN_REQUEST_DURATION.labels(method=method, path=path).observe(duration)


def observe_metrics(func: Callable) -> Callable:
    """Decorator to observe HTTP request metrics."""

    @wraps(func)
    def wrapper(self, *args, **kwargs) -> Any:
        start = perf_counter()
        try:
            result = func(self, *args, **kwargs)
            MetricsRegistry.inc_request("HTTP", "dhan_api", 200)
            return result
        except Exception as e:
            MetricsRegistry.inc_error("HTTP", "dhan_api", type(e).__name__)
            raise
        finally:
            duration = perf_counter() - start
            MetricsRegistry.observe_duration("HTTP", "dhan_api", duration)

    return wrapper


def with_metrics(name: str, tracker: Any = None) -> Callable:
    """Decorator to log metrics using a tracker."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            try:
                result = func(*args, **kwargs)
                if tracker is not None:
                    tracker(name, status="success")
                return result
            except Exception as e:
                if tracker is not None:
                    tracker(name, status="failure", error=type(e).__name__)
                raise

        return wrapper

    return decorator


def with_rate_limit(rate_limiter: Any) -> Callable:
    """Decorator to apply rate limiting using a limiter."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            rate_limiter.acquire()
            return func(*args, **kwargs)

        return wrapper

    return decorator

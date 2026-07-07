"""Health check system — registry + @health_check decorator.

Simple, testable health monitoring for broker adapters.  Each adapter
registers named health checks (connectivity, auth, latency) and the
system aggregates them into a unified status.

Usage::

    from brokers.infrastructure.health import health_registry, health_check

    @health_check("upstox_connectivity")
    async def ping_broker() -> bool:
        ...

    status = health_registry.status()
    # → {"upstox_connectivity": "HEALTHY", ...}
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


# ── Health status ─────────────────────────────────────────────────────────


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    UNKNOWN = "UNKNOWN"


@dataclass
class HealthEntry:
    """Snapshot of a single health check."""

    name: str
    status: HealthStatus
    message: str = ""
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_success: datetime | None = None
    consecutive_failures: int = 0
    latency_ms: float = 0.0
    unhealthy_threshold: int = 3  # consecutive failures before UNHEALTHY


# ── Health registry ───────────────────────────────────────────────────────


class HealthRegistry:
    """Thread-safe registry of named health checks.

    Singleton pattern — use ``health_registry`` module instance.
    """

    def __init__(self) -> None:
        self._entries: dict[str, HealthEntry] = {}
        self._lock = threading.Lock()

    def register(
        self,
        name: str,
        *,
        unhealthy_after_failures: int = 3,
    ) -> None:
        """Register a named health check.

        Args:
            name: Unique check name (e.g. ``"dhan_connectivity"``).
            unhealthy_after_failures: Consecutive failures before UNHEALTHY.
                The check degrades to DEGRADED on the *first* failure;
                this parameter controls how many before UNHEALTHY.
        """
        with self._lock:
            self._entries[name] = HealthEntry(
                name=name,
                status=HealthStatus.UNKNOWN,
                unhealthy_threshold=unhealthy_after_failures,
            )

    def record(self, name: str, success: bool, message: str = "", latency_ms: float = 0.0) -> None:
        """Record a health check result."""
        with self._lock:
            entry = self._entries.get(name)
            if entry is None:
                return

            unhealthy_threshold = entry.unhealthy_threshold if entry.unhealthy_threshold is not None else 3

            now = datetime.now(timezone.utc)
            entry.last_check = now
            entry.latency_ms = latency_ms

            if success:
                entry.status = HealthStatus.HEALTHY
                entry.consecutive_failures = 0
                entry.last_success = now
                entry.message = message or "OK"
            else:
                entry.consecutive_failures += 1
                if entry.consecutive_failures > unhealthy_threshold:
                    entry.status = HealthStatus.UNHEALTHY
                else:
                    entry.status = HealthStatus.DEGRADED
                entry.message = message or "Check failed"

    def status(self) -> dict[str, HealthEntry]:
        """Return snapshots of all registered health checks."""
        with self._lock:
            return {name: HealthEntry(**vars(entry)) for name, entry in self._entries.items()}

    def aggregate(self) -> HealthStatus:
        """Aggregate all checks into a single status.

        - UNHEALTHY if any check is UNHEALTHY
        - DEGRADED if any check is DEGRADED
        - HEALTHY if all are HEALTHY
        - UNKNOWN if no checks registered
        """
        with self._lock:
            if not self._entries:
                return HealthStatus.UNKNOWN
            statuses = {e.status for e in self._entries.values()}
            if HealthStatus.UNHEALTHY in statuses:
                return HealthStatus.UNHEALTHY
            if HealthStatus.DEGRADED in statuses or HealthStatus.UNKNOWN in statuses:
                return HealthStatus.DEGRADED
            return HealthStatus.HEALTHY

    def reset(self) -> None:
        """Clear all entries (useful for testing)."""
        with self._lock:
            self._entries.clear()


# ── Module-level singleton ────────────────────────────────────────────────


health_registry = HealthRegistry()


# ── @health_check decorator ───────────────────────────────────────────────


def _make_timeout_handler(name: str, timeout_ms: float):
    """Build the SIGALRM handler used by the main-thread timeout path."""

    def _timeout_handler(signum, frame):
        raise TimeoutError(f"Health check {name} timed out after {timeout_ms}ms")

    return _timeout_handler


def _run_with_thread_timeout(func, args, kwargs, timeout_ms: float, name: str):
    """Run *func* in a daemon thread and raise TimeoutError if it overruns.

    Used as a fallback when SIGALRM cannot be installed (non-main thread).
    """
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout_ms / 1000.0)
        except concurrent.futures.TimeoutError:
            raise TimeoutError(f"Health check {name} timed out after {timeout_ms}ms") from None


def health_check(
    name: str,
    *,
    unhealthy_after_failures: int = 3,
    timeout_ms: float = 0,
):
    """Decorator that reports function outcomes to the health registry.

    Each invocation of the decorated function automatically records:
    - Success/failure → health status
    - Latency → stored as latency_ms
    - Consecutive failures → DEGRADED on first failure, UNHEALTHY when
      ``consecutive_failures > unhealthy_after_failures``.

    Args:
        name: Unique name for this health check in the registry.
        unhealthy_after_failures: Consecutive failures before UNHEALTHY.
        timeout_ms: If > 0, timeout after this many ms (marks as failure).
    """
    # Register upfront
    health_registry.register(name, unhealthy_after_failures=unhealthy_after_failures)

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            try:
                if timeout_ms > 0:
                    import signal

                    try:
                        old_handler = signal.signal(signal.SIGALRM, _make_timeout_handler(name, timeout_ms))
                        signal.setitimer(signal.ITIMER_REAL, timeout_ms / 1000.0)
                        try:
                            result = func(*args, **kwargs)
                        finally:
                            signal.setitimer(signal.ITIMER_REAL, 0)
                            signal.signal(signal.SIGALRM, old_handler)
                    except (ValueError, OSError):
                        # Signal handlers can only be installed in the main
                        # thread. When called from a worker/background thread,
                        # fall back to a simple wall-clock timeout via a
                        # thread so we never raise and never hang the check.
                        result = _run_with_thread_timeout(func, args, kwargs, timeout_ms, name)
                else:
                    result = func(*args, **kwargs)

                latency = (time.monotonic() - start) * 1000.0
                success = bool(result)
                health_registry.record(name, success=success, message=str(result)[:200], latency_ms=latency)
                return result
            except Exception as exc:
                latency = (time.monotonic() - start) * 1000.0
                health_registry.record(name, success=False, message=str(exc)[:200], latency_ms=latency)
                raise

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.monotonic()
            try:
                if timeout_ms > 0:
                    result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_ms / 1000.0)
                else:
                    result = await func(*args, **kwargs)

                latency = (time.monotonic() - start) * 1000.0
                success = bool(result)
                health_registry.record(name, success=success, message=str(result)[:200], latency_ms=latency)
                return result
            except Exception as exc:
                latency = (time.monotonic() - start) * 1000.0
                health_registry.record(name, success=False, message=str(exc)[:200], latency_ms=latency)
                raise

        if inspect.iscoroutinefunction(func):
            return async_wrapper  # type: ignore[return-value]
        return wrapper  # type: ignore[return-value]

    return decorator

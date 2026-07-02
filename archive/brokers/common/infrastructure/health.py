"""Centralized health check framework for TradeXV2.

Provides a unified health check interface for all system components.
Supports liveness, readiness, and deep health checks.

Usage:
    from infrastructure.health import health_registry, HealthCheck

    @health_registry.register("broker")
    class BrokerHealthCheck(HealthCheck):
        async def check(self) -> HealthStatus:
            ...
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthResult:
    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    latency_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)


class HealthCheck(ABC):
    """Base class for health checks."""

    @abstractmethod
    async def check(self) -> HealthResult:
        ...


class HealthRegistry:
    """Central registry for health checks."""

    def __init__(self) -> None:
        self._checks: dict[str, HealthCheck | Callable[[], HealthResult]] = {}
        self._lock = Lock()

    def register(self, name: str, check: HealthCheck | Callable[[], HealthResult] | None = None):
        """Register a health check."""
        def decorator(obj):
            with self._lock:
                self._checks[name] = obj
            return obj
        if check is not None:
            with self._lock:
                self._checks[name] = check
            return check
        return decorator

    async def run_all(self) -> dict[str, HealthResult]:
        results = {}
        with self._lock:
            checks = dict(self._checks)
        for name, check in checks.items():
            try:
                start = time.monotonic()
                if isinstance(check, HealthCheck):
                    result = await check.check()
                else:
                    result = check()
                result.latency_ms = (time.monotonic() - start) * 1000
                results[name] = result
            except Exception as exc:
                results[name] = HealthResult(
                    status=HealthStatus.UNHEALTHY,
                    message=str(exc),
                )
        return results

    def summary(self, results: dict[str, HealthResult]) -> dict[str, Any]:
        statuses = [r.status for r in results.values()]
        if all(s == HealthStatus.HEALTHY for s in statuses):
            overall = HealthStatus.HEALTHY
        elif any(s == HealthStatus.UNHEALTHY for s in statuses):
            overall = HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.UNKNOWN
        return {
            "status": overall.value,
            "checks": {
                name: {
                    "status": r.status.value,
                    "message": r.message,
                    "latency_ms": round(r.latency_ms, 2),
                }
                for name, r in results.items()
            },
        }


health_registry = HealthRegistry()

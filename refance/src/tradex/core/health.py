"""Health monitoring framework.

Tracks component health and provides aggregated status.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class HealthStatus(Enum):
    """Health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status of a single component."""

    name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    last_check: float = 0.0
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY


@dataclass
class HealthReport:
    """Aggregated health report across all components."""

    status: HealthStatus = HealthStatus.UNKNOWN
    components: dict[str, ComponentHealth] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    @property
    def is_healthy(self) -> bool:
        return all(c.is_healthy for c in self.components.values())

    def add_component(self, health: ComponentHealth) -> None:
        """Add or update a component's health."""
        self.components[health.name] = health
        self._aggregate_status()

    def _aggregate_status(self) -> None:
        """Compute aggregate status from components."""
        if not self.components:
            self.status = HealthStatus.UNKNOWN
            return

        statuses = [c.status for c in self.components.values()]
        if all(s == HealthStatus.HEALTHY for s in statuses):
            self.status = HealthStatus.HEALTHY
        elif any(s == HealthStatus.UNHEALTHY for s in statuses):
            self.status = HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            self.status = HealthStatus.DEGRADED
        else:
            self.status = HealthStatus.UNKNOWN


class HealthMonitor:
    """Tracks health of all SDK components."""

    def __init__(self) -> None:
        self._components: dict[str, ComponentHealth] = {}
        self._check_callbacks: dict[str, Any] = {}

    def register(self, name: str, check_fn: Optional[Any] = None) -> None:
        """Register a component for health monitoring."""
        self._components[name] = ComponentHealth(name=name)
        if check_fn:
            self._check_callbacks[name] = check_fn

    def update(
        self,
        name: str,
        status: HealthStatus,
        message: str = "",
        latency_ms: float = 0.0,
        **metadata: Any,
    ) -> None:
        """Update a component's health status."""
        if name not in self._components:
            self.register(name)

        self._components[name] = ComponentHealth(
            name=name,
            status=status,
            message=message,
            last_check=time.time(),
            latency_ms=latency_ms,
            metadata=metadata,
        )

    async def check_all(self) -> HealthReport:
        """Run all registered health checks."""
        report = HealthReport()

        for name, check_fn in self._check_callbacks.items():
            start = time.monotonic()
            try:
                result = await check_fn()
                latency = (time.monotonic() - start) * 1000
                status = result if isinstance(result, HealthStatus) else HealthStatus.HEALTHY
                self.update(name, status, latency_ms=latency)
            except Exception as e:
                latency = (time.monotonic() - start) * 1000
                self.update(name, HealthStatus.UNHEALTHY, str(e), latency_ms=latency)

        for name, health in self._components.items():
            report.add_component(health)

        return report

    def get_report(self) -> HealthReport:
        """Get current health report without running checks."""
        report = HealthReport()
        for health in self._components.values():
            report.add_component(health)
        return report

"""Lifecycle health model — shared by infrastructure and application layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class HealthState(str, Enum):
    """Lifecycle health state of a managed service."""

    STOPPED = "STOPPED"
    STARTING = "STARTING"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


@dataclass(frozen=True)
class HealthStatus:
    """A point-in-time health snapshot for a service."""

    state: HealthState
    service: str
    detail: str = ""
    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "state": self.state.value,
            "last_check": self.last_check.isoformat(),
            "detail": self.detail,
            "metrics": dict(self.metrics),
        }

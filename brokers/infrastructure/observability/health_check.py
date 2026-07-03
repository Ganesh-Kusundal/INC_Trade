"""Broker health checks for the centralized infrastructure health registry.

Registers per-broker connectivity and WebSocket health checks with the
``health_registry`` singleton so the SRE layer can poll a single endpoint
for system-wide health.

Usage (called automatically by broker factories)::

    from brokers.infrastructure.observability.health_check import register_broker_health_check

    register_broker_health_check("dhan", gateway)

The health check evaluates:

1. **REST API reachability** — via ``gateway.describe()``.
2. **WebSocket stream health** — via ``ObservabilityProvider.get_connection_status()``
   when the gateway implements the protocol.

Status mapping:

- ``OK``       — REST reachable and all WebSocket streams connected
                 (or no streams configured, e.g. analytics-only mode).
- ``DEGRADED`` — REST reachable, some but not all streams connected.
- ``DOWN``     — REST unreachable, or all WebSocket streams disconnected.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    """Health status enumeration.

    OK: Fully operational — all checks passing.
    DEGRADED: Partially operational — some checks failing or performance degraded.
    DOWN: Non-operational — critical checks failing.
    """

    OK = "OK"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


@dataclass
class HealthResult:
    """Result of a health check evaluation.

    Attributes
    ----------
    status:
        Health status (OK, DEGRADED, or DOWN).
    message:
        Human-readable description of the health state.
    details:
        Optional dictionary with additional context about the check.
    """

    status: HealthStatus
    message: str
    details: dict[str, Any] | None = None


class HealthCheck(ABC):
    """Abstract base class for health checks.

    Subclasses must implement the ``check()`` method to perform
    the actual health evaluation.
    """

    @abstractmethod
    async def check(self) -> HealthResult:
        """Perform the health check.

        Returns
        -------
        HealthResult
            The result of the health check evaluation.
        """
        ...


class HealthRegistry:
    """Registry for health checks.

    Maintains a collection of named health checks that can be
    evaluated together to produce a system-wide health snapshot.
    """

    def __init__(self) -> None:
        self._checks: dict[str, HealthCheck] = {}

    def register(self, name: str, check: HealthCheck) -> None:
        """Register a health check.

        Parameters
        ----------
        name:
            Unique identifier for the health check.
        check:
            The health check instance to register.
        """
        self._checks[name] = check
        logger.info("health_check_registered", extra={"name": name})

    def unregister(self, name: str) -> bool:
        """Remove a health check from the registry.

        Parameters
        ----------
        name:
            Name of the health check to remove.

        Returns
        -------
        bool
            True if the check was found and removed, False otherwise.
        """
        if name in self._checks:
            del self._checks[name]
            logger.info("health_check_unregistered", extra={"name": name})
            return True
        return False

    async def check_all(self) -> dict[str, HealthResult]:
        """Evaluate all registered health checks.

        Returns
        -------
        dict[str, HealthResult]
            Dictionary mapping check names to their results.
        """
        results: dict[str, HealthResult] = {}
        for name, check in self._checks.items():
            try:
                results[name] = await check.check()
            except Exception as exc:
                logger.exception(
                    "health_check_failed",
                    extra={"name": name, "error": str(exc)},
                )
                results[name] = HealthResult(
                    status=HealthStatus.DOWN,
                    message=f"Health check failed: {type(exc).__name__}: {exc}",
                )
        return results

    def get(self, name: str) -> HealthCheck | None:
        """Get a registered health check by name.

        Parameters
        ----------
        name:
            Name of the health check.

        Returns
        -------
        HealthCheck | None
            The health check if found, None otherwise.
        """
        return self._checks.get(name)


# Global health registry singleton
health_registry = HealthRegistry()


class BrokerConnectivityHealthCheck(HealthCheck):
    """Checks broker REST and WebSocket connectivity.

    The check is intentionally lightweight — it reads cached connection
    state from the gateway rather than making network calls — so it is
    safe to invoke on every SRE poll interval.

    Parameters
    ----------
    broker_id:
        Canonical broker identifier (e.g. ``"dhan"``, ``"upstox"``).
    gateway:
        The broker gateway instance. May implement ``ObservabilityProvider``
        for WebSocket stream visibility; if it does not, only REST
        reachability is checked.
    """

    def __init__(self, broker_id: str, gateway: Any) -> None:
        self._broker_id = broker_id
        self._gateway = gateway

    async def check(self) -> HealthResult:
        details: dict[str, Any] = {}

        # ── 1. REST API reachability ──────────────────────────────────
        try:
            desc = self._gateway.describe()
            details["rest_api"] = "reachable"
            details["instrument_count"] = desc.get("instrument_count", 0)
        except Exception as exc:
            return HealthResult(
                status=HealthStatus.DOWN,
                message=f"REST API unreachable: {type(exc).__name__}: {exc}",
                details={"rest_api": f"error: {exc}"},
            )

        # ── 2. WebSocket stream health ────────────────────────────────
        connection_status: dict[str, bool] = {}
        if hasattr(self._gateway, "get_connection_status"):
            try:
                connection_status = self._gateway.get_connection_status()
                details["streams"] = {
                    name: "connected" if ok else "disconnected"
                    for name, ok in connection_status.items()
                }
            except Exception as exc:
                details["streams_error"] = str(exc)
                logger.debug(
                    "health_check_stream_status_failed",
                    extra={"broker_id": self._broker_id, "error": str(exc)},
                )

        # No WebSocket streams configured (analytics-only, paper, etc.)
        if not connection_status:
            return HealthResult(
                status=HealthStatus.OK,
                message="REST API reachable, no WebSocket streams configured",
                details=details,
            )

        # Evaluate WebSocket connectivity
        connected = [name for name, ok in connection_status.items() if ok]
        disconnected = [name for name, ok in connection_status.items() if not ok]

        if not disconnected:
            return HealthResult(
                status=HealthStatus.OK,
                message=f"All {len(connected)} stream(s) connected",
                details=details,
            )
        elif connected:
            return HealthResult(
                status=HealthStatus.DEGRADED,
                message=(
                    f"{len(connected)}/{len(connection_status)} stream(s) connected; "
                    f"disconnected: {disconnected}"
                ),
                details=details,
            )
        else:
            return HealthResult(
                status=HealthStatus.DOWN,
                message=f"All WebSocket streams disconnected: {list(connection_status.keys())}",
                details=details,
            )


def register_broker_health_check(broker_id: str, gateway: Any) -> None:
    """Register a broker connectivity health check with the global registry.

    Idempotent: re-registering the same ``broker_id`` replaces the previous
    check (e.g. on token-refresh reconnection).

    Parameters
    ----------
    broker_id:
        Canonical broker identifier.
    gateway:
        The broker gateway instance (must support ``describe()`` at minimum).
    """
    check = BrokerConnectivityHealthCheck(broker_id, gateway)
    health_registry.register(f"broker.{broker_id}", check)
    logger.info(
        "broker_health_check_registered",
        extra={"broker_id": broker_id, "check_name": f"broker.{broker_id}"},
    )


__all__ = [
    "BrokerConnectivityHealthCheck",
    "HealthCheck",
    "HealthRegistry",
    "HealthResult",
    "HealthStatus",
    "health_registry",
    "register_broker_health_check",
]

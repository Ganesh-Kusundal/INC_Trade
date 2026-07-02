"""Broker health checks for the centralized infrastructure health registry.

Registers per-broker connectivity and WebSocket health checks with the
``infrastructure.health.health_registry`` singleton so the SRE layer can
poll a single endpoint for system-wide health.

Usage (called automatically by broker factories)::

    from brokers.common.observability.health_check import register_broker_health_check

    register_broker_health_check("dhan", gateway)

The health check evaluates:

1. **REST API reachability** — via ``gateway.describe()``.
2. **WebSocket stream health** — via ``ObservabilityProvider.get_connection_status()``
   when the gateway implements the protocol.

Status mapping:

- ``HEALTHY``   — REST reachable and all WebSocket streams connected
                  (or no streams configured, e.g. analytics-only mode).
- ``DEGRADED``  — REST reachable, some but not all streams connected.
- ``UNHEALTHY`` — REST unreachable, or all WebSocket streams disconnected.
"""

from __future__ import annotations

import logging
from typing import Any

from infrastructure.health import HealthCheck, HealthResult, HealthStatus

logger = logging.getLogger(__name__)


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
                status=HealthStatus.UNHEALTHY,
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
                status=HealthStatus.HEALTHY,
                message="REST API reachable, no WebSocket streams configured",
                details=details,
            )

        # Evaluate WebSocket connectivity
        connected = [name for name, ok in connection_status.items() if ok]
        disconnected = [name for name, ok in connection_status.items() if not ok]

        if not disconnected:
            return HealthResult(
                status=HealthStatus.HEALTHY,
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
                status=HealthStatus.UNHEALTHY,
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
    from infrastructure.health import health_registry

    check = BrokerConnectivityHealthCheck(broker_id, gateway)
    health_registry.register(f"broker.{broker_id}", check)
    logger.info(
        "broker_health_check_registered",
        extra={"broker_id": broker_id, "check_name": f"broker.{broker_id}"},
    )

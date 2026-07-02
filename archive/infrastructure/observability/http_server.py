"""HTTP observability server — /healthz, /readyz, /metrics.

The system previously had no way for an operator
to see if a process was alive, ready to serve traffic, or what its
internal state looked like. This module:

* Serves ``/healthz`` — liveness probe (the process is up).
* Serves ``/readyz`` — readiness probe (the broker is connected and
  every registered service is HEALTHY).
* Serves ``/metrics`` — Prometheus text exposition format, generated
  from :class:`EventMetrics`, :class:`LifecycleManager.health_snapshot`,
  and the broker gateway's runtime state.

The server is a :class:`ManagedService` so it integrates with the
LifecycleManager added in Wave 2. The CLI's ``BrokerService`` can
optionally register an instance; production deployments wire it up
in their own entry points.

Excluded from the initial observability surface:

* TLS / mTLS — left to a reverse proxy or service mesh. The server
  binds plain HTTP. An operator who needs TLS terminates it at the
  load balancer.
* Authentication — the endpoints are unauthenticated. This is
  acceptable for a localhost-only observability surface; do not
  expose to the public internet.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from aiohttp import web

from domain.constants import (
    DEFAULT_STOP_TIMEOUT_SECONDS,
    OBSERVABILITY_DEFAULT_HOST,
    OBSERVABILITY_DEFAULT_PORT,
)
from infrastructure.lifecycle.lifecycle import (
    HealthState,
    LifecycleManager,
    ManagedService,
)
from infrastructure.metrics.registry import metrics_registry

logger = logging.getLogger(__name__)


def _extract_event_metrics_from_registry() -> dict[str, dict[str, int]]:
    """Extract EventMetrics-style counters from MetricsRegistry.

    EventMetrics registers counters with names starting with
    ``event_metrics__`` and labels ``{event_type, outcome}``.
    This function reconstructs the nested dict format expected by
    ``render_prometheus_metrics``.
    """
    from infrastructure.observability.event_metrics import _COUNTER_PREFIX

    snap = metrics_registry.snapshot_detailed()
    event_counters = snap.get("counters", {})
    out: dict[str, dict[str, int]] = defaultdict(dict)
    for name, info in event_counters.items():
        if name.startswith(_COUNTER_PREFIX):
            labels = info.get("labels", {})
            event_type = labels.get("event_type", "")
            outcome = labels.get("outcome", "")
            if event_type and outcome:
                out[event_type][outcome] = int(info.get("value", 0))
    return dict(out)


# ── Prometheus text format helpers ────────────────────────────────────────


def _escape_label_value(v: str) -> str:
    """Escape a label value for Prometheus text format."""
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render_prometheus_metrics(
    event_metrics_snapshot: dict[str, dict[str, int]],
    lifecycle_health: dict[str, dict[str, Any]],
    extra_gauges: dict[str, float] | None = None,
) -> str:
    """Render a Prometheus text exposition payload.

    Args:
        event_metrics_snapshot: the dict from ``EventMetrics.snapshot()``,
            shape ``{event_type: {outcome: count}}``.
        lifecycle_health: the dict from
            ``LifecycleManager.health_snapshot()``, shape
            ``{service_name: {state, detail, metrics, last_check}}``.
        extra_gauges: optional dict of gauge_name -> value. Useful for
            things like ``daily_pnl`` or ``kill_switch_active``.

    Returns:
        A string in the Prometheus text exposition format (version 0.0.4).
    """
    lines: list[str] = []

    # ── Counters from EventMetrics ──────────────────────────────────────
    lines.append("# HELP tradexv2_events_total Events by type and outcome.")
    lines.append("# TYPE tradexv2_events_total counter")
    for event_type, outcomes in sorted(event_metrics_snapshot.items()):
        for outcome, count in sorted(outcomes.items()):
            labels = (
                f'event_type="{_escape_label_value(event_type)}",'
                f' outcome="{_escape_label_value(outcome)}"'
            )
            lines.append(f"tradexv2_events_total{{{labels}}} {count}")

    # ── Gauges for each ManagedService ─────────────────────────────────
    lines.append(
        "# HELP tradexv2_service_health Managed service health state (0=STOPPED, 1=STARTING, 2=HEALTHY, 3=DEGRADED, 4=UNHEALTHY, 5=STOPPING, 6=FAILED)."
    )
    lines.append("# TYPE tradexv2_service_health gauge")
    state_to_int = {
        HealthState.STOPPED: 0,
        HealthState.STARTING: 1,
        HealthState.HEALTHY: 2,
        HealthState.DEGRADED: 3,
        HealthState.UNHEALTHY: 4,
        HealthState.STOPPING: 5,
        HealthState.FAILED: 6,
    }
    for service_name, snap in sorted(lifecycle_health.items()):
        labels = f'service="{_escape_label_value(service_name)}"'
        state_str = snap.get("state", "STOPPED")
        # The state may be a string (after to_dict()) rather than the
        # enum, so handle both.
        try:
            enum_state = HealthState(state_str)
            value = state_to_int[enum_state]
        except (ValueError, KeyError):
            value = 0
        lines.append(f"tradexv2_service_health{{{labels}}} {value}")

    # ── Extra gauges ───────────────────────────────────────────────────
    if extra_gauges:
        lines.append("# HELP tradexv2_gauges Application-specific gauges.")
        lines.append("# TYPE tradexv2_gauges gauge")
        for name, value in sorted(extra_gauges.items()):
            try:
                lines.append(f"tradexv2_{name} {float(value)}")
            except (TypeError, ValueError):
                continue

    return "\n".join(lines) + "\n"


# ── HTTP server (ManagedService) ─────────────────────────────────────────


class HttpObservabilityServer(ManagedService):
    """aiohttp server exposing /healthz, /readyz, /metrics.

    Parameters
    ----------
    host:
        Bind address. Default ``"127.0.0.1"`` (loopback only). Override
        to ``"0.0.0.0"`` to expose to a sidecar / service mesh.
    port:
        TCP port. Default ``8765`` — a non-privileged port unlikely to
        clash with common services. Pick a different one in CI.
    lifecycle:
        Optional :class:`LifecycleManager`. When provided, the server
        reports each registered service's health in ``/readyz`` and
        ``/metrics``.
    event_metrics:
        Optional :class:`EventMetrics`. When provided, its snapshot is
        rendered in ``/metrics``.
    extra_gauges_fn:
        Optional callable returning a ``dict[str, float]`` of extra
        gauges to render in ``/metrics``. Called on every scrape.
    """

    name = "http.observability"

    def __init__(
        self,
        host: str = OBSERVABILITY_DEFAULT_HOST,
        port: int = OBSERVABILITY_DEFAULT_PORT,
        lifecycle: LifecycleManager | None = None,
        event_metrics: Any | None = None,
        extra_gauges_fn: Any | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._lifecycle = lifecycle
        self._event_metrics = event_metrics
        self._extra_gauges_fn = extra_gauges_fn
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._serve_thread: threading.Thread | None = None
        # Metrics
        self._request_count = 0
        self._started_at: datetime | None = None
        self._last_error: str | None = None

    @property
    def port(self) -> int:
        """Public accessor for the server port."""
        return self._port

    @property
    def host(self) -> str:
        """Public accessor for the server host."""
        return self._host

    # ── aiohttp request handlers ───────────────────────────────────────

    async def _handle_healthz(self, request: web.Request) -> web.Response:
        """Liveness: the process is up. Always 200 unless the event
        loop is broken."""
        self._request_count += 1
        return web.json_response(
            {
                "status": "alive",
                "service": self.name,
                "uptime_seconds": (
                    (datetime.now(timezone.utc) - self._started_at).total_seconds()
                    if self._started_at
                    else 0.0
                ),
                "requests_served": self._request_count,
            }
        )

    async def _handle_readyz(self, request: web.Request) -> web.Response:
        """Readiness: every registered ManagedService is HEALTHY (or
        DEGRADED, which is still serving). 503 if any service is
        FAILED, STOPPED (after start_all), or UNHEALTHY.
        Also checks the FastAPI HealthRegistry for consistency."""
        self._request_count += 1

        # Check LifecycleManager services
        lifecycle_not_ready: list[tuple[str, str]] = []
        lifecycle_services: dict[str, str] = {}
        if self._lifecycle is not None:
            snap = self._lifecycle.health_snapshot()
            registered = bool(snap)
            ready_states = {HealthState.HEALTHY, HealthState.DEGRADED}
            for name, info in snap.items():
                try:
                    state = HealthState(info["state"])
                except (ValueError, KeyError):
                    state = HealthState.FAILED
                lifecycle_services[name] = info.get("state", "UNKNOWN")
                if state in ready_states:
                    continue
                if state == HealthState.STOPPED and not registered:
                    continue
                lifecycle_not_ready.append((name, state.value))

        # Check HealthRegistry (FastAPI /health checks)
        registry_not_ready: list[tuple[str, str]] = {}
        try:

            from infrastructure.health import health_registry

            results = await health_registry.run_all()
            for name, result in results.items():
                status_val = result.status.value
                registry_not_ready[name] = status_val
                if status_val not in ("healthy", "degraded"):
                    lifecycle_not_ready.append((f"health_registry.{name}", status_val))
        except Exception:
            pass

        body: dict[str, Any] = {
            "status": "ready" if not lifecycle_not_ready else "not_ready",
            "services": lifecycle_services,
        }
        if registry_not_ready:
            body["health_registry"] = registry_not_ready
        if lifecycle_not_ready:
            body["not_ready"] = lifecycle_not_ready
            return web.json_response(body, status=503)
        return web.json_response(body, status=200)

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        """Prometheus text exposition format."""
        self._request_count += 1
        event_snap: dict[str, dict[str, int]] = {}
        try:
            event_snap = _extract_event_metrics_from_registry()
        except Exception as exc:
            logger.warning("event_metrics_registry_extract_failed: %s", exc)
            if self._event_metrics is not None and hasattr(self._event_metrics, "snapshot"):
                try:
                    event_snap = self._event_metrics.snapshot()
                except Exception as inner_exc:
                    logger.warning("event_metrics_snapshot_failed: %s", inner_exc)
        lifecycle_snap: dict[str, dict[str, Any]] = {}
        if self._lifecycle is not None:
            try:
                lifecycle_snap = self._lifecycle.health_snapshot()
                for name, info in lifecycle_snap.items():
                    if hasattr(info, "to_dict"):
                        lifecycle_snap[name] = info.to_dict()
            except Exception as exc:
                logger.warning("lifecycle_health_snapshot_failed: %s", exc)
        extra: dict[str, float] = {}
        if self._extra_gauges_fn is not None:
            try:
                extra = self._extra_gauges_fn() or {}
            except Exception as exc:
                logger.warning("extra_gauges_fn_failed: %s", exc)
        body = render_prometheus_metrics(event_snap, lifecycle_snap, extra)
        return web.Response(
            text=body,
            content_type="text/plain",
            charset="utf-8",
        )

    async def _handle_root(self, request: web.Request) -> web.Response:
        """A tiny landing page so a curl to / returns something useful."""
        self._request_count += 1
        return web.json_response(
            {
                "service": self.name,
                "endpoints": {
                    "/healthz": "liveness probe (always 200 if process is up)",
                    "/readyz": "readiness probe (503 if any ManagedService is FAILED/UNHEALTHY)",
                    "/metrics": "Prometheus text exposition",
                },
            }
        )

    # ── ManagedService protocol ────────────────────────────────────────

    def start(self) -> None:
        """Start the HTTP server in a dedicated background event loop.

        ``aiohttp`` is async; we run it in a dedicated thread with its
        own event loop. This avoids the awkward dance of integrating
        with the caller's event loop.

        The :class:`web.TCPSite` is constructed *inside* the thread
        after ``runner.setup()`` runs — aiohttp 3.14+ raises
        ``RuntimeError("Call runner.setup() before making a site")`` if
        the site is constructed before setup. This was the bug the
        earlier version had.
        """
        if self._runner is not None:
            logger.debug("http_observability_already_running")
            return
        self._last_error = None
        self._started_at = datetime.now(timezone.utc)
        app = web.Application()
        app.router.add_get("/", self._handle_root)
        app.router.add_get("/healthz", self._handle_healthz)
        app.router.add_get("/readyz", self._handle_readyz)
        app.router.add_get("/metrics", self._handle_metrics)

        runner = web.AppRunner(app)
        self._runner = runner

        # Run the runner in a dedicated thread with its own event loop.
        ready = threading.Event()
        start_error: list[BaseException] = []
        port_holder: list[int] = []

        def _serve() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop  # stored for stop() to call loop.stop()
            try:
                loop.run_until_complete(runner.setup())
                # Construct the TCPSite AFTER setup — aiohttp 3.14+
                # requires this.
                site = web.TCPSite(runner, host=self._host, port=self._port)
                loop.run_until_complete(site.start())
                self._site = site
                # Capture the actual bound port (port=0 means OS-assigned).
                try:
                    port_holder.append(site._server.sockets[0].getsockname()[1])
                except Exception as exc:
                    logger.debug("http_port_capture_failed: %s", exc)
                ready.set()
                # Run forever until the loop is stopped.
                loop.run_forever()
            except BaseException as exc:
                start_error.append(exc)
                ready.set()
            finally:
                try:
                    loop.run_until_complete(runner.cleanup())
                except Exception as exc:
                    logger.debug("http_runner_cleanup_failed: %s", exc)
                loop.close()

        t = threading.Thread(
            target=_serve,
            name="http.observability",
            daemon=True,
        )
        self._serve_thread = t
        t.start()
        # Wait for the server to be ready (or fail). Bounded wait so
        # a failing bind (port in use) surfaces immediately.
        if not ready.wait(timeout=5.0):
            self._last_error = "server failed to start within 5s"
            logger.error("http_observability_start_timeout")
            return
        if start_error:
            self._last_error = repr(start_error[0])
            logger.error("http_observability_start_failed: %s", start_error[0])
            return
        actual_port = port_holder[0] if port_holder else self._port
        logger.info(
            "http_observability_started",
            extra={"host": self._host, "port": actual_port},
        )

    def stop(self, timeout_seconds: float = DEFAULT_STOP_TIMEOUT_SECONDS) -> None:
        """Stop the HTTP server. Bounded by ``timeout_seconds``.

        Schedules ``loop.stop()`` on the event-loop thread, then waits
        for the thread to finish. The daemon thread will otherwise be
        reaped at GC, but we explicitly stop it for clean lifecycle
        management and to avoid stale port bindings on restart.
        """
        runner = self._runner
        loop = self._loop
        thread = self._serve_thread
        self._site = None
        self._runner = None
        self._loop = None
        self._serve_thread = None
        if runner is None or loop is None:
            return
        try:
            # Close the underlying server socket first so no new
            # connections are accepted.
            if hasattr(runner, "_server") and runner._server is not None:
                try:
                    runner._server.close()
                except Exception as exc:
                    logger.debug("http_server_close_failed: %s", exc)
            # Stop the event loop from the calling thread.
            loop.call_soon_threadsafe(loop.stop)
            # Wait for the serve thread to finish (bounded).
            if thread is not None and thread.is_alive():
                thread.join(timeout=timeout_seconds)
        except Exception as exc:
            logger.warning("http_observability_stop: %s", exc)
        logger.info("http_observability_stopped")

    def health(self):
        from infrastructure.lifecycle.lifecycle import HealthState, HealthStatus

        if self._last_error:
            state = HealthState.DEGRADED
            detail = self._last_error
        elif self._site is not None:
            state = HealthState.HEALTHY
            detail = f"listening on {self._host}:{self._port}"
        else:
            state = HealthState.STOPPED
            detail = "not started"
        return HealthStatus(
            state=state,
            service=self.name,
            last_check=datetime.now(timezone.utc),
            detail=detail,
            metrics={
                "requests_served": self._request_count,
                "host": self._host,
                "port": self._port,
            },
        )

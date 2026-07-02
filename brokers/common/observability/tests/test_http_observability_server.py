"""Tests for Phase B / B8 + B9: HTTP observability server and Prometheus exporter.

Covers:
  - render_prometheus_metrics produces valid Prometheus text format
  - HttpObservabilityServer is a ManagedService
  - /healthz returns 200 with process info
  - /readyz returns 200 when no lifecycle / all services healthy,
    503 when any service is FAILED/UNHEALTHY
  - /metrics returns Prometheus format with EventMetrics + lifecycle health
  - start() / stop() are idempotent and drain within timeout
  - Service is registerable with a LifecycleManager
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from brokers.common.observability.event_metrics import EventMetrics
from brokers.common.observability.http_server import (
    HttpObservabilityServer,
    render_prometheus_metrics,
)
from infrastructure.lifecycle.lifecycle import (
    HealthState,
    HealthStatus,
    LifecycleManager,
    ManagedService,
)
from infrastructure.metrics.registry import metrics_registry


@pytest.fixture(autouse=True)
def _reset_global_metrics_registry() -> None:
    """EventMetrics delegates to a process-global registry; reset for isolation."""
    metrics_registry.reset_all()
    yield
    metrics_registry.reset_all()

# ── Prometheus renderer ───────────────────────────────────────────────────


def test_render_empty_metrics() -> None:
    """Empty input produces a valid (though minimal) Prometheus text."""
    out = render_prometheus_metrics({}, {}, None)
    # Must have HELP/TYPE lines even with no data.
    assert "# HELP tradexv2_events_total" in out
    assert "# TYPE tradexv2_events_total counter" in out
    assert "# HELP tradexv2_service_health" in out
    assert "# TYPE tradexv2_service_health gauge" in out


def test_render_event_counters() -> None:
    """EventMetrics counters are rendered as Prometheus counters."""
    em = EventMetrics()
    em.inc("TICK", "published")
    em.inc("TICK", "published")  # count 2
    em.inc("ORDER_PLACED", "handler_error:ValueError")
    out = render_prometheus_metrics(em.snapshot(), {})
    assert 'tradexv2_events_total{event_type="TICK", outcome="published"} 2' in out
    assert (
        'tradexv2_events_total{event_type="ORDER_PLACED", outcome="handler_error:ValueError"} 1'
        in out
    )


def test_render_lifecycle_health_gauge() -> None:
    """Each ManagedService becomes a gauge for its state."""
    em = EventMetrics()

    class _Rec(ManagedService):
        name = "rec"

        def start(self):
            pass

        def stop(self, timeout_seconds=5.0):
            pass

        def health(self):
            return HealthStatus(
                state=HealthState.HEALTHY,
                service="rec",
                last_check=datetime.now(timezone.utc),
            )

    class _Dead(ManagedService):
        name = "dead"

        def start(self):
            pass

        def stop(self, timeout_seconds=5.0):
            pass

        def health(self):
            return HealthStatus(
                state=HealthState.FAILED,
                service="dead",
                last_check=datetime.now(timezone.utc),
            )

    lc = LifecycleManager()
    lc.register(_Rec())
    lc.register(_Dead())
    lc.start_all()
    # health_snapshot() already returns a dict[str, dict] shape, no
    # to_dict() needed. The render function expects this shape.
    snap_dict = lc.health_snapshot()

    out = render_prometheus_metrics(em.snapshot(), snap_dict)
    # HEALTHY = 2
    assert 'tradexv2_service_health{service="rec"} 2' in out
    # FAILED = 6
    assert 'tradexv2_service_health{service="dead"} 6' in out


def test_render_extra_gauges() -> None:
    out = render_prometheus_metrics({}, {}, {"daily_pnl": -1500.5, "kill_switch_active": 0})
    assert "tradexv2_daily_pnl -1500.5" in out
    assert "tradexv2_kill_switch_active 0" in out


def test_render_label_value_escaping() -> None:
    """Special characters in label values are escaped."""
    em = EventMetrics()
    em.inc('EVT-WITH"QUOTE', "line\nbreak")
    out = render_prometheus_metrics(em.snapshot(), {})
    # The quote is escaped, the newline is escaped.
    assert '\\"' in out
    assert "\\n" in out


def test_render_is_prometheus_text_format() -> None:
    """Output ends with a newline and uses no tabs (Prometheus spec)."""
    out = render_prometheus_metrics({}, {}, {})
    assert out.endswith("\n")
    assert "\t" not in out


# ── HttpObservabilityServer: ManagedService compliance ──────────────────


def test_http_server_is_managed_service() -> None:
    s = HttpObservabilityServer(port=0)  # port 0 = let OS pick
    assert isinstance(s, ManagedService)
    assert s.name == "http.observability"
    assert hasattr(s, "start")
    assert hasattr(s, "stop")
    assert hasattr(s, "health")


def test_health_before_start() -> None:
    s = HttpObservabilityServer()
    h = s.health()
    assert h.state == HealthState.STOPPED
    assert h.service == "http.observability"


# ── /healthz, /readyz, /metrics handlers ──────────────────────────────────


@pytest.fixture
def server():
    s = HttpObservabilityServer(
        host="127.0.0.1",
        port=0,
        event_metrics=EventMetrics(),
    )
    s.start()
    # Find the actual port (aiohttp stores it on the site).
    yield s
    s.stop(timeout_seconds=2.0)


def _get_port(server: HttpObservabilityServer) -> int:
    """Extract the actual bound port from the running aiohttp site."""
    site = server._site
    # aiohttp >=3.8 stores sockets on _server.sockets; we pull the
    # port from the first socket.
    sockets = site._server.sockets if site else []
    if sockets:
        return sockets[0].getsockname()[1]
    return server._port


@pytest.mark.asyncio
async def test_healthz_returns_200(server: HttpObservabilityServer) -> None:
    import aiohttp

    port = _get_port(server)
    async with (
        aiohttp.ClientSession() as session,
        session.get(f"http://127.0.0.1:{port}/healthz") as resp,
    ):
        assert resp.status == 200
        data = await resp.json()
    assert data["status"] == "alive"
    assert data["service"] == "http.observability"
    assert "uptime_seconds" in data
    assert "requests_served" in data


@pytest.mark.asyncio
async def test_readyz_no_lifecycle_returns_200(server: HttpObservabilityServer) -> None:
    """When no lifecycle is wired, /readyz returns 200."""
    import aiohttp

    port = _get_port(server)
    async with (
        aiohttp.ClientSession() as session,
        session.get(f"http://127.0.0.1:{port}/readyz") as resp,
    ):
        assert resp.status == 200
        data = await resp.json()
    assert data["status"] == "ready"
    assert data["services"] == {}


@pytest.mark.asyncio
async def test_metrics_renders_event_metrics(server: HttpObservabilityServer) -> None:
    """The /metrics endpoint serializes EventMetrics correctly."""
    import aiohttp

    server._event_metrics.inc("TICK", "published")
    server._event_metrics.inc("TICK", "dispatched")
    port = _get_port(server)
    async with (
        aiohttp.ClientSession() as session,
        session.get(f"http://127.0.0.1:{port}/metrics") as resp,
    ):
        assert resp.status == 200
        assert resp.content_type == "text/plain"
        text = await resp.text()
    assert 'tradexv2_events_total{event_type="TICK", outcome="published"} 1' in text
    assert 'tradexv2_events_total{event_type="TICK", outcome="dispatched"} 1' in text


@pytest.mark.asyncio
async def test_root_endpoint_returns_endpoints(server: HttpObservabilityServer) -> None:
    import aiohttp

    port = _get_port(server)
    async with aiohttp.ClientSession() as session, session.get(f"http://127.0.0.1:{port}/") as resp:
        assert resp.status == 200
        data = await resp.json()
    assert "endpoints" in data
    assert "/healthz" in data["endpoints"]
    assert "/readyz" in data["endpoints"]
    assert "/metrics" in data["endpoints"]


# ── /readyz with lifecycle ───────────────────────────────────────────────


def test_readyz_returns_503_when_a_service_failed() -> None:
    """If a registered ManagedService is in FAILED state, /readyz
    must return 503 so a load balancer can take this pod out of
    rotation."""
    s = HttpObservabilityServer(host="127.0.0.1", port=0)

    class _Dead(ManagedService):
        name = "dead-svc"

        def start(self):
            pass

        def stop(self, timeout_seconds=5.0):
            pass

        def health(self):
            return HealthStatus(
                state=HealthState.FAILED,
                service="dead-svc",
                last_check=datetime.now(timezone.utc),
            )

    class _Healthy(ManagedService):
        name = "healthy-svc"

        def start(self):
            pass

        def stop(self, timeout_seconds=5.0):
            pass

        def health(self):
            return HealthStatus(
                state=HealthState.HEALTHY,
                service="healthy-svc",
                last_check=datetime.now(timezone.utc),
            )

    lc = LifecycleManager()
    lc.register(_Healthy())
    lc.register(_Dead())
    lc.start_all()

    s._lifecycle = lc
    s.start()
    try:
        import asyncio

        # Simulate the request directly
        port = _get_port(s)

        async def _check():
            import aiohttp

            async with (
                aiohttp.ClientSession() as session,
                session.get(f"http://127.0.0.1:{port}/readyz") as resp,
            ):
                return resp.status, await resp.json()

        status, body = asyncio.run(_check())
        assert status == 503
        assert body["status"] == "not_ready"
        assert "dead-svc" in body["not_ready"][0]
    finally:
        s.stop(timeout_seconds=2.0)


# ── Lifecycle integration ──────────────────────────────────────────────


def test_server_can_be_registered_with_lifecycle() -> None:
    """HttpObservabilityServer is itself a ManagedService and can be
    registered with a LifecycleManager."""
    lc = LifecycleManager()
    server = HttpObservabilityServer(port=0)
    lc.register(server)
    assert "http.observability" in lc.service_names()
    lc.start_all()
    try:
        # Health should be HEALTHY
        snap = lc.health_snapshot()
        assert "http.observability" in snap
    finally:
        lc.stop_all()


def test_server_stop_idempotent() -> None:
    s = HttpObservabilityServer(port=0)
    s.start()
    s.stop(timeout_seconds=2.0)
    # Second stop is a no-op
    s.stop(timeout_seconds=2.0)


def test_extra_gauges_fn_failure_does_not_break_metrics() -> None:
    """If the extra_gauges_fn raises, the /metrics endpoint must
    still return 200 (with no extras)."""
    s = HttpObservabilityServer(
        host="127.0.0.1",
        port=0,
        extra_gauges_fn=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    s.start()
    try:
        import asyncio

        port = _get_port(s)

        async def _check():
            import aiohttp

            async with (
                aiohttp.ClientSession() as session,
                session.get(f"http://127.0.0.1:{port}/metrics") as resp,
            ):
                return resp.status, await resp.text()

        status, text = asyncio.run(_check())
        assert status == 200
        # The /metrics body is still well-formed
        assert "# HELP tradexv2_events_total" in text
    finally:
        s.stop(timeout_seconds=2.0)


def test_extra_gauges_fn_provides_custom_gauges() -> None:
    """The extra_gauges_fn is called on every /metrics scrape."""
    counter = {"n": 0}

    def fn():
        counter["n"] += 1
        return {"scrape_count": float(counter["n"])}

    s = HttpObservabilityServer(host="127.0.0.1", port=0, extra_gauges_fn=fn)
    s.start()
    try:
        import asyncio

        port = _get_port(s)

        async def _scrape():
            import aiohttp

            async with (
                aiohttp.ClientSession() as session,
                session.get(f"http://127.0.0.1:{port}/metrics") as resp,
            ):
                return await resp.text()

        text1 = asyncio.run(_scrape())
        text2 = asyncio.run(_scrape())
        assert "tradexv2_scrape_count 1" in text1
        assert "tradexv2_scrape_count 2" in text2
    finally:
        s.stop(timeout_seconds=2.0)

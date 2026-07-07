"""Tests for new infrastructure modules: event_bus, metrics, tracing, cache, time_service, config/schema."""

from __future__ import annotations


import pytest

from brokers.domain.events import DomainEvent


# ── Event Bus ────────────────────────────────────────────────────────────


class TestEventBus:
    def test_publish_and_subscribe(self) -> None:
        from brokers.infrastructure.event_bus import EventBus

        bus = EventBus()
        received = []
        bus.subscribe("TICK", lambda e: received.append(e))

        event = DomainEvent.now("TICK", {"ltp": 100.0})
        bus.publish(event)

        assert len(received) == 1
        assert received[0].payload == {"ltp": 100.0}

    def test_unsubscribe(self) -> None:
        from brokers.infrastructure.event_bus import EventBus

        bus = EventBus()
        received = []
        token = bus.subscribe("TICK", lambda e: received.append(e))
        bus.unsubscribe(token)

        bus.publish(DomainEvent.now("TICK", {}))
        assert len(received) == 0

    def test_multiple_handlers(self) -> None:
        from brokers.infrastructure.event_bus import EventBus

        bus = EventBus()
        count1, count2 = [], []
        bus.subscribe("TICK", lambda e: count1.append(1))
        bus.subscribe("TICK", lambda e: count2.append(1))

        bus.publish(DomainEvent.now("TICK", {}))
        assert len(count1) == 1
        assert len(count2) == 1

    def test_handler_failure_does_not_stop_others(self) -> None:
        from brokers.infrastructure.event_bus import EventBus

        bus = EventBus()
        results = []

        def bad_handler(e):
            raise ValueError("boom")

        bus.subscribe("TICK", bad_handler)
        bus.subscribe("TICK", lambda e: results.append("ok"))

        bus.publish(DomainEvent.now("TICK", {}))
        assert results == ["ok"]

    def test_subscriber_count(self) -> None:
        from brokers.infrastructure.event_bus import EventBus

        bus = EventBus()
        assert bus.subscriber_count() == 0
        bus.subscribe("TICK", lambda e: None)
        bus.subscribe("TICK", lambda e: None)
        assert bus.subscriber_count("TICK") == 2
        assert bus.subscriber_count() == 2

    def test_clear(self) -> None:
        from brokers.infrastructure.event_bus import EventBus

        bus = EventBus()
        bus.subscribe("TICK", lambda e: None)
        bus.clear()
        assert bus.subscriber_count() == 0

    def test_sequence_number(self) -> None:
        from brokers.infrastructure.event_bus import EventBus

        bus = EventBus()
        events = []
        bus.subscribe("TICK", lambda e: events.append(e))

        bus.publish(DomainEvent.now("TICK", {}))
        bus.publish(DomainEvent.now("TICK", {}))

        assert events[0].sequence_number == 1
        assert events[1].sequence_number == 2


# ── Metrics ──────────────────────────────────────────────────────────────


class TestCounter:
    def test_inc(self) -> None:
        from brokers.infrastructure.metrics import Counter

        c = Counter("test_counter")
        c.inc()
        assert c.value == 1
        c.inc(5)
        assert c.value == 6

    def test_reset(self) -> None:
        from brokers.infrastructure.metrics import Counter

        c = Counter("test_counter")
        c.inc(10)
        c.reset()
        assert c.value == 0


class TestGauge:
    def test_set_inc_dec(self) -> None:
        from brokers.infrastructure.metrics import Gauge

        g = Gauge("test_gauge")
        g.set(10)
        assert g.value == 10
        g.inc(5)
        assert g.value == 15
        g.dec(3)
        assert g.value == 12


class TestHistogram:
    def test_observe(self) -> None:
        from brokers.infrastructure.metrics import Histogram

        h = Histogram("test_hist")
        h.observe(0.5)
        h.observe(1.5)
        assert h.count == 2
        assert h.total == 2.0

    def test_bucket_counts(self) -> None:
        from brokers.infrastructure.metrics import Histogram

        h = Histogram("test_hist", buckets=[1.0, 5.0])
        h.observe(0.5)
        h.observe(3.0)
        h.observe(10.0)
        buckets = h.bucket_counts()
        assert buckets == [(1.0, 1), (5.0, 2), (float("inf"), 3)]


class TestTimer:
    def test_context_manager(self) -> None:
        from brokers.infrastructure.metrics import Timer

        t = Timer("test_timer")
        with t.time():
            pass
        assert t.count == 1
        assert t.mean >= 0

    def test_percentiles(self) -> None:
        from brokers.infrastructure.metrics import Timer

        t = Timer("test_timer")
        for i in range(100):
            t.observe(float(i))
        assert t.p50 == 50.0
        assert t.p95 == 95.0
        assert t.p99 == 99.0


class TestMetricsRegistry:
    def test_singleton_counters(self) -> None:
        from brokers.infrastructure.metrics import MetricsRegistry

        reg = MetricsRegistry()
        c1 = reg.counter("test")
        c2 = reg.counter("test")
        assert c1 is c2

    def test_snapshot(self) -> None:
        from brokers.infrastructure.metrics import MetricsRegistry

        reg = MetricsRegistry()
        reg.counter("requests").inc(5)
        reg.gauge("connections").set(10)
        snap = reg.snapshot()
        assert snap["counters"]["requests"] == 5
        assert snap["gauges"]["connections"] == 10

    def test_reset_all(self) -> None:
        from brokers.infrastructure.metrics import MetricsRegistry

        reg = MetricsRegistry()
        reg.counter("c").inc(10)
        reg.gauge("g").set(20)
        reg.reset_all()
        assert reg.snapshot()["counters"]["c"] == 0
        assert reg.snapshot()["gauges"]["g"] == 0


# ── Tracing ──────────────────────────────────────────────────────────────


class TestTracer:
    def test_span_lifecycle(self) -> None:
        from brokers.infrastructure.tracing import Tracer

        t = Tracer()
        with t.span("test_op") as s:
            s.set_tag("key", "value")
        spans = t.finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "test_op"
        assert spans[0].tags["key"] == "value"
        assert spans[0].duration_ms is not None
        assert spans[0].duration_ms >= 0

    def test_nested_spans(self) -> None:
        from brokers.infrastructure.tracing import Tracer

        t = Tracer()
        with t.span("outer") as outer:
            with t.span("inner") as inner:
                inner.set_tag("inner_key", 42)
        spans = t.finished_spans()
        assert len(spans) == 2
        assert inner.parent_span_id == outer.span_id

    def test_error_recording(self) -> None:
        from brokers.infrastructure.tracing import Tracer

        t = Tracer()
        with pytest.raises(ValueError):
            with t.span("failing"):
                raise ValueError("boom")
        spans = t.finished_spans()
        assert spans[0].status == "ERROR"
        assert "boom" in spans[0].error

    def test_to_dict(self) -> None:
        from brokers.infrastructure.tracing import Tracer

        t = Tracer()
        with t.span("op") as s:
            s.set_tag("k", "v")
        d = t.finished_spans()[0].to_dict()
        assert d["name"] == "op"
        assert d["tags"]["k"] == "v"

    def test_clear_finished(self) -> None:
        from brokers.infrastructure.tracing import Tracer

        t = Tracer()
        with t.span("op"):
            pass
        assert len(t.finished_spans()) == 1
        t.clear_finished()
        assert len(t.finished_spans()) == 0


# ── Cache ────────────────────────────────────────────────────────────────


class TestMemoryCache:
    def test_get_set(self) -> None:
        from brokers.infrastructure.cache import MemoryCache

        c = MemoryCache()
        c.set("k", "v")
        assert c.get("k") == "v"

    def test_get_missing(self) -> None:
        from brokers.infrastructure.cache import MemoryCache

        c = MemoryCache()
        assert c.get("missing") is None

    def test_ttl_expiration(self) -> None:
        from brokers.infrastructure.cache import MemoryCache

        c = MemoryCache()
        c.set("k", "v", ttl=0)
        # TTL=0 means no expiration
        assert c.get("k") == "v"

    def test_delete(self) -> None:
        from brokers.infrastructure.cache import MemoryCache

        c = MemoryCache()
        c.set("k", "v")
        c.delete("k")
        assert c.get("k") is None

    def test_clear(self) -> None:
        from brokers.infrastructure.cache import MemoryCache

        c = MemoryCache()
        c.set("a", 1)
        c.set("b", 2)
        c.clear()
        assert c.size == 0

    def test_has(self) -> None:
        from brokers.infrastructure.cache import MemoryCache

        c = MemoryCache()
        c.set("k", "v")
        assert c.has("k") is True
        assert c.has("missing") is False

    def test_maxsize_eviction(self) -> None:
        from brokers.infrastructure.cache import MemoryCache

        c = MemoryCache(maxsize=5)
        for i in range(10):
            c.set(f"k{i}", i)
        assert c.size <= 5

    def test_snapshot(self) -> None:
        from brokers.infrastructure.cache import MemoryCache

        c = MemoryCache()
        c.set("a", 1)
        c.set("b", 2)
        snap = c.snapshot()
        assert snap == {"a": 1, "b": 2}


class TestCachedDecorator:
    def test_caches_result(self) -> None:
        from brokers.infrastructure.cache import MemoryCache, cached

        cache = MemoryCache()
        call_count = 0

        @cached(cache=cache)
        def expensive(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        assert expensive(5) == 10
        assert expensive(5) == 10
        assert call_count == 1  # second call uses cache


# ── Time Service ─────────────────────────────────────────────────────────


class TestTimeService:
    def test_now(self) -> None:
        from brokers.infrastructure.time_service import TimeService

        ts = TimeService()
        now = ts.now()
        assert now.tzinfo is not None

    def test_exchange_now(self) -> None:
        from brokers.infrastructure.time_service import TimeService

        ts = TimeService()
        nse_now = ts.exchange_now("NSE")
        assert nse_now.tzinfo is not None

    def test_unknown_exchange(self) -> None:
        from brokers.infrastructure.time_service import TimeService

        ts = TimeService()
        with pytest.raises(ValueError, match="Unknown exchange"):
            ts.exchange_now("UNKNOWN")

    def test_format_timestamp(self) -> None:
        from brokers.infrastructure.time_service import TimeService

        ts = TimeService()
        formatted = ts.format_timestamp()
        assert isinstance(formatted, str)

    def test_parse_iso(self) -> None:
        from brokers.infrastructure.time_service import TimeService

        ts = TimeService()
        dt = ts.parse_iso("2026-01-15T10:30:00Z")
        assert dt.year == 2026

    def test_epoch_now(self) -> None:
        from brokers.infrastructure.time_service import TimeService

        ts = TimeService()
        assert isinstance(ts.epoch_now(), int)

    def test_epoch_ms(self) -> None:
        from brokers.infrastructure.time_service import TimeService

        ts = TimeService()
        assert isinstance(ts.epoch_ms(), int)
        assert ts.epoch_ms() > 1_000_000_000_000


# ── Config Schema ────────────────────────────────────────────────────────


class TestConfigSchema:
    def test_dhan_config_defaults(self) -> None:
        from brokers.config.schema import DhanConfig

        c = DhanConfig()
        assert c.environment == "LIVE"
        assert c.allow_live_orders is False

    def test_upstox_config_defaults(self) -> None:
        from brokers.config.schema import UpstoxConfig

        c = UpstoxConfig()
        assert c.environment == "LIVE"
        assert c.auth_mode == "STATIC"

    def test_api_config_defaults(self) -> None:
        from brokers.config.schema import ApiConfig

        c = ApiConfig()
        assert c.host == "127.0.0.1"
        assert c.port == 8080

    def test_trading_config_defaults(self) -> None:
        from brokers.config.schema import TradingConfig

        c = TradingConfig()
        assert c.orchestrator_dry_run is True
        assert c.smart_routing is True
        assert c.primary_broker == "dhan"

    def test_app_config_from_env(self) -> None:
        from brokers.config.schema import AppConfig

        c = AppConfig.from_env()
        assert c.app_env in ("dev", "staging", "prod")
        assert c.log_level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

    def test_load_dhan_config(self) -> None:
        from brokers.config.schema import load_dhan_config

        c = load_dhan_config()
        assert isinstance(c.client_id, str)

    def test_load_upstox_config(self) -> None:
        from brokers.config.schema import load_upstox_config

        c = load_upstox_config()
        assert isinstance(c.access_token, str)

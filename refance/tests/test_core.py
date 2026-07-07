"""Tests for core framework components."""

import asyncio

import pytest
from tradex.core.cache import TTLCache
from tradex.core.errors import (
    AuthenticationError,
    BrokerError,
    RateLimitError,
    ValidationError,
    map_provider_error,
)
from tradex.core.events import DomainEvent, EventBus
from tradex.core.health import HealthMonitor, HealthStatus
from tradex.core.metrics import MetricsCollector
from tradex.core.rate_limiter import SlidingWindowCounter, TokenBucket
from tradex.core.retry import CircuitBreaker
from tradex.core.validation import Validator

# --- Error Tests ---


class TestErrors:
    def test_broker_error_creation(self):
        err = BrokerError("test error", code="TEST-001")
        assert str(err) == "test error"
        assert err.code == "TEST-001"
        assert not err.retryable

    def test_error_mapping(self):
        err = map_provider_error("DH-904", "Rate limited", provider="dhan")
        assert isinstance(err, RateLimitError)
        assert err.retryable
        assert err.context.provider == "dhan"

    def test_auth_error_mapping(self):
        err = map_provider_error("DH-901", "Invalid token")
        assert isinstance(err, AuthenticationError)
        assert not err.retryable

    def test_error_with_context(self):
        err = BrokerError("test", code="T")
        err2 = err.with_context(provider="dhan", endpoint="/orders")
        assert err2.context.provider == "dhan"
        assert err2.context.endpoint == "/orders"


# --- Event Tests ---


class TestEventBus:
    def test_subscribe_and_publish(self):
        bus = EventBus()
        received = []

        @bus.on(DomainEvent)
        async def handler(event):
            received.append(event)

        event = DomainEvent(source="test")
        asyncio.run(bus.publish(event))
        assert len(received) == 1
        assert received[0].event_id == event.event_id

    def test_multiple_handlers(self):
        bus = EventBus()
        count = [0]

        @bus.on(DomainEvent)
        async def h1(event):
            count[0] += 1

        @bus.on(DomainEvent)
        async def h2(event):
            count[0] += 10

        event = DomainEvent()
        asyncio.run(bus.publish(event))
        assert count[0] == 11

    def test_unsubscribe(self):
        bus = EventBus()
        received = []

        async def handler(event):
            received.append(event)

        bus.subscribe(DomainEvent, handler)
        bus.unsubscribe(DomainEvent, handler)

        event = DomainEvent()
        asyncio.run(bus.publish(event))
        assert len(received) == 0

    def test_event_history(self):
        bus = EventBus()

        async def handler(event):
            pass

        bus.subscribe(DomainEvent, handler)

        for _ in range(5):
            asyncio.run(bus.publish(DomainEvent()))

        history = bus.get_history(DomainEvent, limit=3)
        assert len(history) == 3

    def test_handler_count(self):
        bus = EventBus()

        @bus.on(DomainEvent)
        async def h1(e):
            pass

        @bus.on(DomainEvent)
        async def h2(e):
            pass

        assert bus.handler_count == 2


# --- Cache Tests ---


class TestTTLCache:
    @pytest.mark.asyncio
    async def test_put_and_get(self):
        cache = TTLCache[str, str](max_size=100, default_ttl=60.0)
        await cache.put("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_miss(self):
        cache = TTLCache[str, str](max_size=100, default_ttl=60.0)
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_expiry(self):
        cache = TTLCache[str, str](max_size=100, default_ttl=0.01)
        await cache.put("key1", "value1")
        await asyncio.sleep(0.02)
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_invalidation(self):
        cache = TTLCache[str, str](max_size=100, default_ttl=60.0)
        await cache.put("key1", "value1")
        removed = await cache.invalidate("key1")
        assert removed
        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        cache = TTLCache[str, str](max_size=2, default_ttl=60.0)
        await cache.put("a", "1")
        await cache.put("b", "2")
        await cache.put("c", "3")  # Should evict "a"
        result = await cache.get("a")
        assert result is None
        result = await cache.get("b")
        assert result == "2"

    @pytest.mark.asyncio
    async def test_stats(self):
        cache = TTLCache[str, str](max_size=100, default_ttl=60.0)
        await cache.put("a", "1")
        await cache.get("a")
        await cache.get("b")
        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1


# --- Rate Limiter Tests ---


class TestTokenBucket:
    @pytest.mark.asyncio
    async def test_acquire(self):
        bucket = TokenBucket(capacity=10, refill_rate=10.0)
        wait = await bucket.acquire(1)
        assert wait == 0.0
        assert bucket.available >= 8

    @pytest.mark.asyncio
    async def test_try_acquire(self):
        bucket = TokenBucket(capacity=2, refill_rate=1.0)
        assert await bucket.try_acquire(1)
        assert await bucket.try_acquire(1)
        assert not await bucket.try_acquire(1)


class TestSlidingWindow:
    @pytest.mark.asyncio
    async def test_acquire(self):
        sw = SlidingWindowCounter(window_seconds=1.0, max_requests=3)
        assert await sw.try_acquire()
        assert await sw.try_acquire()
        assert await sw.try_acquire()
        assert not await sw.try_acquire()


# --- Circuit Breaker Tests ---


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_normal_operation(self):
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == "closed"

    @pytest.mark.asyncio
    async def test_opens_on_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            await cb.record_failure()
        assert cb.is_open

    @pytest.mark.asyncio
    async def test_resets_on_success(self):
        cb = CircuitBreaker(failure_threshold=3)
        await cb.record_failure()
        await cb.record_success()
        assert not cb.is_open


# --- Validation Tests ---


class TestValidation:
    def test_required(self):
        with pytest.raises(ValidationError):
            Validator.check(None, "name").required().raise_if_invalid()

    def test_positive(self):
        with pytest.raises(ValidationError):
            Validator.check(-1, "qty").positive().raise_if_invalid()

    def test_one_of(self):
        with pytest.raises(ValidationError):
            Validator.check("INVALID", "side").one_of(["BUY", "SELL"]).raise_if_invalid()

    def test_valid(self):
        Validator.check("BUY", "side").one_of(
            ["BUY", "SELL"]
        ).raise_if_invalid()  # Should not raise

    def test_custom(self):
        (Validator.check(100, "val").custom(lambda x: x > 50, "must be > 50").raise_if_invalid())


# --- Health Tests ---


class TestHealth:
    def test_health_monitor(self):
        monitor = HealthMonitor()
        monitor.register("test_component")
        monitor.update("test_component", HealthStatus.HEALTHY, "All good")
        report = monitor.get_report()
        assert report.is_healthy

    def test_unhealthy_component(self):
        monitor = HealthMonitor()
        monitor.register("comp1")
        monitor.register("comp2")
        monitor.update("comp1", HealthStatus.HEALTHY)
        monitor.update("comp2", HealthStatus.UNHEALTHY)
        report = monitor.get_report()
        assert not report.is_healthy


# --- Metrics Tests ---


class TestMetrics:
    def test_counter(self):
        m = MetricsCollector()
        m.increment("orders")
        m.increment("orders")
        assert m.get_counter("orders") == 2

    def test_gauge(self):
        m = MetricsCollector()
        m.gauge("connections", 5)
        assert m.get_gauge("connections") == 5

    def test_histogram(self):
        m = MetricsCollector()
        for v in [10, 20, 30]:
            m.histogram("latency", v)
        stats = m.get_histogram_stats("latency")
        assert stats["count"] == 3
        assert stats["min"] == 10
        assert stats["max"] == 30

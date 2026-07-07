"""Performance benchmarks — latency and throughput measurements."""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock


class TestCachePerformance:
    """Benchmark TTLCache under load."""

    @pytest.mark.asyncio
    async def test_cache_read_throughput(self):
        from tradex.core.cache import TTLCache
        cache = TTLCache[str, str](max_size=10000, default_ttl=60.0)
        
        # Populate
        for i in range(1000):
            await cache.put(f"key_{i}", f"value_{i}")
        
        # Benchmark reads
        start = time.perf_counter()
        for i in range(10000):
            await cache.get(f"key_{i % 1000}")
        elapsed = time.perf_counter() - start
        
        ops_per_sec = 10000 / elapsed
        print(f"\nCache reads: {ops_per_sec:,.0f} ops/sec ({elapsed*1000:.1f}ms for 10K reads)")
        assert ops_per_sec > 1000  # At least 1K reads/sec

    @pytest.mark.asyncio
    async def test_cache_write_throughput(self):
        from tradex.core.cache import TTLCache
        cache = TTLCache[str, str](max_size=10000, default_ttl=60.0)
        
        start = time.perf_counter()
        for i in range(10000):
            await cache.put(f"key_{i}", f"value_{i}")
        elapsed = time.perf_counter() - start
        
        ops_per_sec = 10000 / elapsed
        print(f"\nCache writes: {ops_per_sec:,.0f} ops/sec ({elapsed*1000:.1f}ms for 10K writes)")
        assert ops_per_sec > 1000


class TestEventBusPerformance:
    """Benchmark EventBus publish/subscribe."""

    @pytest.mark.asyncio
    async def test_event_publish_throughput(self):
        from tradex.core.events import EventBus, DomainEvent
        bus = EventBus()
        count = [0]
        
        @bus.on(DomainEvent)
        async def handler(e):
            count[0] += 1
        
        start = time.perf_counter()
        for _ in range(5000):
            await bus.publish(DomainEvent(source="bench"))
        elapsed = time.perf_counter() - start
        
        ops_per_sec = 5000 / elapsed
        print(f"\nEvent publish: {ops_per_sec:,.0f} ops/sec ({elapsed*1000:.1f}ms for 5K events)")
        assert count[0] == 5000
        assert ops_per_sec > 500

    @pytest.mark.asyncio
    async def test_event_multi_handler_throughput(self):
        from tradex.core.events import EventBus, DomainEvent
        bus = EventBus()
        counts = [0, 0, 0]
        
        @bus.on(DomainEvent)
        async def h1(e): counts[0] += 1
        @bus.on(DomainEvent)
        async def h2(e): counts[1] += 1
        @bus.on(DomainEvent)
        async def h3(e): counts[2] += 1
        
        start = time.perf_counter()
        for _ in range(2000):
            await bus.publish(DomainEvent())
        elapsed = time.perf_counter() - start
        
        print(f"\n3-handler publish: {2000/elapsed:,.0f} ops/sec")
        assert all(c == 2000 for c in counts)


class TestRateLimiterPerformance:
    """Benchmark rate limiter overhead."""

    @pytest.mark.asyncio
    async def test_token_bucket_acquire_latency(self):
        from tradex.core.rate_limiter import TokenBucket
        bucket = TokenBucket(capacity=10000, refill_rate=100000.0)
        
        start = time.perf_counter()
        for _ in range(10000):
            await bucket.try_acquire()
        elapsed = time.perf_counter() - start
        
        print(f"\nTokenBucket try_acquire: {10000/elapsed:,.0f} ops/sec")
        assert elapsed < 5.0  # Should be fast


class TestValueObjectPerformance:
    """Benchmark value object creation."""

    def test_money_creation_throughput(self):
        from tradex.domain.value_objects import Money
        from decimal import Decimal
        
        start = time.perf_counter()
        for i in range(10000):
            Money(Decimal(str(i + 0.99)))
        elapsed = time.perf_counter() - start
        
        print(f"\nMoney creation: {10000/elapsed:,.0f} ops/sec")
        assert elapsed < 2.0

    def test_price_alignment_throughput(self):
        from tradex.domain.value_objects import Price
        from decimal import Decimal
        
        start = time.perf_counter()
        for i in range(10000):
            Price(Decimal(str(i + 0.12)), Decimal("0.05"))
        elapsed = time.perf_counter() - start
        
        print(f"\nPrice alignment: {10000/elapsed:,.0f} ops/sec")
        assert elapsed < 2.0


class TestStreamEnginePerformance:
    """Benchmark stream message processing."""

    @pytest.mark.asyncio
    async def test_message_dispatch_latency(self):
        from tradex.streaming.engine import StreamEngine, StreamConfig
        import json
        
        config = StreamConfig(url="wss://test", reconnect=False)
        engine = StreamEngine(config)
        
        processed = [0]
        async def handler(data):
            processed[0] += 1
        engine.on_message(handler)
        
        # Directly test dispatch without WebSocket
        msg = {"type": "tick", "ltp": 2450}
        start = time.perf_counter()
        for _ in range(5000):
            await engine._on_message(msg)
        elapsed = time.perf_counter() - start
        
        print(f"\nMessage dispatch: {5000/elapsed:,.0f} ops/sec")
        assert processed[0] == 5000

"""Soak tests — extended operation stability, memory leaks, resource cleanup."""
import asyncio
import gc
import sys
import pytest
from unittest.mock import AsyncMock


class TestEventBusSoak:
    """Verify EventBus doesn't leak memory over many publish cycles."""

    @pytest.mark.asyncio
    async def test_repeated_publish_subscribe_cycle(self):
        from tradex.core.events import EventBus, DomainEvent
        
        bus = EventBus()
        gc.collect()
        
        # Simulate 100 subscribe/unsubscribe cycles
        for cycle in range(100):
            received = []
            
            async def handler(e, _rec=received):
                _rec.append(e)
            
            bus.subscribe(DomainEvent, handler)
            
            for _ in range(50):
                await bus.publish(DomainEvent(source=f"cycle_{cycle}"))
            
            bus.unsubscribe(DomainEvent, handler)
            assert len(received) == 50
        
        # Verify no handler accumulation
        assert bus.handler_count == 0
        # Verify history is bounded
        assert len(bus._published) <= 1000

    @pytest.mark.asyncio
    async def test_history_bounded_after_many_events(self):
        from tradex.core.events import EventBus, DomainEvent
        
        bus = EventBus()
        
        async def noop(e):
            pass
        bus.subscribe(DomainEvent, noop)
        
        # Publish 5000 events (more than maxlen=1000)
        for _ in range(5000):
            await bus.publish(DomainEvent())
        
        assert len(bus._published) == 1000  # Bounded by deque maxlen


class TestCacheSoak:
    """Verify cache doesn't leak memory and evicts properly."""

    @pytest.mark.asyncio
    async def test_cache_eviction_under_sustained_load(self):
        from tradex.core.cache import TTLCache
        
        cache = TTLCache[int, str](max_size=100, default_ttl=60.0)
        
        # Write 10000 entries (100x the max size)
        for i in range(10000):
            await cache.put(i, f"value_{i}")
        
        size = await cache.size()
        assert size <= 100  # Should not exceed max_size
        
        # Verify LRU: recent entries should exist
        latest = await cache.get(9999)
        assert latest == "value_9999"
        
        # Verify old entries were evicted
        oldest = await cache.get(0)
        assert oldest is None

    @pytest.mark.asyncio
    async def test_cache_ttl_expiry_cleanup(self):
        from tradex.core.cache import TTLCache
        
        cache = TTLCache[str, str](max_size=1000, default_ttl=0.05)
        
        # Fill cache
        for i in range(100):
            await cache.put(f"k{i}", f"v{i}")
        
        # Wait for expiry
        await asyncio.sleep(0.1)
        
        # Cleanup expired
        removed = await cache.cleanup()
        assert removed == 100
        assert await cache.size() == 0

    @pytest.mark.asyncio
    async def test_cache_stats_accuracy(self):
        from tradex.core.cache import TTLCache
        
        cache = TTLCache[str, str](max_size=100, default_ttl=60.0)
        
        await cache.put("a", "1")
        await cache.get("a")  # hit
        await cache.get("b")  # miss
        await cache.get("a")  # hit
        await cache.get("c")  # miss
        
        stats = cache.stats
        assert stats["hits"] == 2
        assert stats["misses"] == 2
        assert stats["hit_rate"] == 0.5


class TestOrderFeedSoak:
    """Verify OrderFeed handles sustained order flow."""

    @pytest.mark.asyncio
    async def test_sustained_order_flow(self):
        from tradex.core.events import EventBus
        from tradex.streaming.order_feed import OrderFeed
        from tradex.domain.events import OrderStatusChanged
        
        bus = EventBus()
        feed = OrderFeed(event_bus=bus)
        status_count = [0]
        
        @bus.on(OrderStatusChanged)
        async def on_status(e):
            status_count[0] += 1
        
        # Simulate 200 orders going through full lifecycle
        for i in range(200):
            oid = f"ORD_{i:04d}"
            await feed.process_update({"orderId": oid, "orderStatus": "PLACED", "securityId": "1"})
            await feed.process_update({"orderId": oid, "orderStatus": "OPEN", "filledQty": "0", "pendingQty": "10"})
            await feed.process_update({"orderId": oid, "orderStatus": "TRADED", "filledQty": "10", "averagePrice": "100"})
        
        # Each order: PLACED + OPEN + TRADED = 3 status changes
        assert status_count[0] == 600
        # Cache should hold all 200 orders
        assert len(feed.cached_orders) == 200


class TestStreamEngineSoak:
    """Verify StreamEngine resource cleanup."""

    @pytest.mark.asyncio
    async def test_connect_disconnect_cycle_cleanup(self):
        from tradex.streaming.engine import StreamEngine, StreamConfig
        
        for _ in range(20):
            config = StreamConfig(url="wss://test", reconnect=False)
            engine = StreamEngine(config)
            
            mock_ws = AsyncMock()
            mock_ws.recv = AsyncMock(side_effect=asyncio.CancelledError)
            
            async def create_ws():
                return mock_ws
            
            await engine.connect(create_ws)
            assert engine.is_connected
            
            await engine.disconnect()
            assert not engine.is_connected
            assert engine._ws is None
            # Allow cancelled tasks to finish
            await asyncio.sleep(0.05)
            assert len(engine._tasks) == 0 or all(t.done() for t in engine._tasks)

    @pytest.mark.asyncio
    async def test_message_queue_bounded(self):
        from tradex.streaming.engine import StreamEngine, StreamConfig
        
        config = StreamConfig(url="wss://test", reconnect=False, message_buffer_size=10)
        engine = StreamEngine(config)
        
        # Try to overflow the queue
        for i in range(20):
            try:
                engine._message_queue.put_nowait({"seq": i})
            except asyncio.QueueFull:
                pass
        
        assert engine._message_queue.qsize() <= 10


class TestRateLimiterSoak:
    """Verify rate limiter window cleanup."""

    @pytest.mark.asyncio
    async def test_sliding_window_cleanup(self):
        from tradex.core.rate_limiter import SlidingWindowCounter
        
        sw = SlidingWindowCounter(window_seconds=0.1, max_requests=5)
        
        # Fill the window
        for _ in range(5):
            await sw.acquire()
        
        assert sw.current_count == 5
        
        # Wait for window to expire
        await asyncio.sleep(0.15)
        
        # Window should be clean
        assert sw.current_count == 0
        
        # Should be able to acquire again
        assert await sw.try_acquire()

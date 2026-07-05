"""Tests for TypedIdempotencyCache / OrderResultCache."""

from __future__ import annotations

import threading
import time

from inc_trade.utils.idempotency_cache import OrderResultCache


class TestIdempotencyCache:
    def setup_method(self):
        self.cache = OrderResultCache(ttl_seconds=60.0, max_size=100)

    def test_put_and_get(self):
        self.cache.put("order-1", "result-1")
        assert self.cache.get("order-1") == "result-1"

    def test_get_missing_returns_none(self):
        assert self.cache.get("nonexistent") is None

    def test_different_keys(self):
        self.cache.put("order-1", "r1")
        self.cache.put("order-2", "r2")
        assert self.cache.get("order-1") == "r1"
        assert self.cache.get("order-2") == "r2"

    def test_clear(self):
        self.cache.put("order-1", "r1")
        self.cache.clear()
        assert self.cache.get("order-1") is None


class TestIdempotencyTTL:
    def test_expired_entries_evicted(self):
        cache = OrderResultCache(ttl_seconds=0.05, max_size=100)
        cache.put("order-1", "r1")
        time.sleep(0.1)
        assert cache.get("order-1") is None


class TestIdempotencyLRU:
    def test_max_size_eviction(self):
        cache = OrderResultCache(ttl_seconds=3600, max_size=3)
        cache.put("a", 1)
        cache.put("b", 2)
        cache.put("c", 3)
        cache.put("d", 4)
        assert len(cache._cache) <= 3


class TestIdempotencyThreadSafety:
    def test_concurrent_put(self):
        cache = OrderResultCache(ttl_seconds=60, max_size=100)
        barrier = threading.Barrier(10)

        def try_put():
            barrier.wait()
            cache.put("shared-key", "value")

        threads = [threading.Thread(target=try_put) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert cache.get("shared-key") == "value"


class TestIdempotencyLock:
    def setup_method(self):
        self.cache = OrderResultCache(ttl_seconds=60, max_size=100)

    def test_lock_context_manager(self):
        with self.cache.lock("key-1"):
            self.cache.put("key-1", "val")
        assert self.cache.get("key-1") == "val"

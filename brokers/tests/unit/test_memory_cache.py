"""Tests for MemoryCache — thread-safe, TTL-based in-memory cache."""

from __future__ import annotations

import time

from brokers.infrastructure.cache.memory_cache import MemoryCache


class TestMemoryCacheBasic:
    """Basic set/get/delete operations."""

    def test_set_and_get(self) -> None:
        cache = MemoryCache()
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"

    def test_get_missing_key(self) -> None:
        cache = MemoryCache()
        assert cache.get("nonexistent") is None

    def test_get_after_delete(self) -> None:
        cache = MemoryCache()
        cache.set("key", "value")
        cache.delete("key")
        assert cache.get("key") is None

    def test_delete_returns_true_for_existing(self) -> None:
        cache = MemoryCache()
        cache.set("key", "value")
        assert cache.delete("key") is True

    def test_delete_returns_false_for_missing(self) -> None:
        cache = MemoryCache()
        assert cache.delete("nonexistent") is False

    def test_clear(self) -> None:
        cache = MemoryCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None
        assert cache.size == 0

    def test_overwrite_existing_key(self) -> None:
        cache = MemoryCache()
        cache.set("key", "old")
        cache.set("key", "new")
        assert cache.get("key") == "new"


class TestMemoryCacheTTL:
    """TTL expiration behavior."""

    def test_expires_after_ttl(self) -> None:
        cache = MemoryCache()
        cache.set("key", "value", ttl_seconds=0.05)
        time.sleep(0.1)
        assert cache.get("key") is None

    def test_not_expired_before_ttl(self) -> None:
        cache = MemoryCache()
        cache.set("key", "value", ttl_seconds=10.0)
        assert cache.get("key") == "value"

    def test_default_ttl(self) -> None:
        cache = MemoryCache(default_ttl_seconds=0.05)
        cache.set("key", "value")
        time.sleep(0.1)
        assert cache.get("key") is None

    def test_none_ttl_means_no_expiration(self) -> None:
        cache = MemoryCache()
        cache.set("key", "value", ttl_seconds=None)
        time.sleep(0.05)
        assert cache.get("key") == "value"


class TestMemoryCacheStaleWhileRevalidate:
    """Stale-while-revalidate pattern."""

    def test_get_stale_not_stale(self) -> None:
        cache = MemoryCache()
        cache.set("key", "value", ttl_seconds=10.0)
        value, is_stale = cache.get_stale("key", max_age_seconds=5.0)
        assert value == "value"
        assert is_stale is False

    def test_get_stale_missing(self) -> None:
        cache = MemoryCache()
        value, is_stale = cache.get_stale("missing", max_age_seconds=5.0)
        assert value is None
        assert is_stale is False

    def test_get_stale_expired(self) -> None:
        cache = MemoryCache()
        cache.set("key", "value", ttl_seconds=0.05)
        time.sleep(0.1)
        value, is_stale = cache.get_stale("key", max_age_seconds=0.01)
        assert value is None
        assert is_stale is False  # expired, not just stale


class TestMemoryCacheBulk:
    """Batch operations."""

    def test_get_many(self) -> None:
        cache = MemoryCache()
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        result = cache.get_many(["a", "b", "missing"])
        assert result == {"a": 1, "b": 2}

    def test_set_many(self) -> None:
        cache = MemoryCache()
        cache.set_many({"x": 10, "y": 20, "z": 30})
        assert cache.get("x") == 10
        assert cache.get("y") == 20
        assert cache.get("z") == 30

    def test_get_many_empty_list(self) -> None:
        cache = MemoryCache()
        assert cache.get_many([]) == {}

    def test_set_many_empty_dict(self) -> None:
        cache = MemoryCache()
        cache.set_many({})
        assert cache.size == 0


class TestMemoryCacheLRUEviction:
    """LRU eviction when max_entries exceeded."""

    def test_evicts_oldest_when_full(self) -> None:
        cache = MemoryCache(max_entries=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # Should evict "a"
        assert cache.get("a") is None  # Evicted
        assert cache.get("b") == 2
        assert cache.get("c") == 3
        assert cache.get("d") == 4
        assert cache.size == 3

    def test_recently_used_not_evicted(self) -> None:
        cache = MemoryCache(max_entries=3)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        # Access "a" so it becomes recently used
        cache.get("a")
        cache.set("d", 4)  # Should evict "b" (oldest unaccessed)
        assert cache.get("a") == 1  # Not evicted (recently used)
        assert cache.get("b") is None  # Evicted
        assert cache.size == 3


class TestMemoryCacheThreadSafety:
    """Thread safety under concurrent access."""

    def test_concurrent_set_and_get(self) -> None:
        import threading

        cache = MemoryCache()
        errors = []

        def worker(key: str) -> None:
            try:
                for _ in range(100):
                    cache.set(key, key)
                    assert cache.get(key) == key
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(f"key{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"

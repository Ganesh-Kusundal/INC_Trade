"""Tests for cross-broker idempotency cache."""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from brokers.common.idempotency import (
    CacheEntry,
    IdempotencyCacheProtocol,
    IdempotencyStats,
    MemoryIdempotencyCache,
    RedisIdempotencyCache,
)


# ── MemoryIdempotencyCache: Basic CRUD ────────────────────────────────────────


class TestMemoryIdempotencyCacheBasic:
    def test_put_new_key_returns_true(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        assert cache.put_if_absent("order-1", {"order_id": "ord_1"}) is True

    def test_get_returns_stored_value(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        cache.put_if_absent("order-1", {"order_id": "ord_1"})
        assert cache.get("order-1") == {"order_id": "ord_1"}

    def test_get_missing_returns_none(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        assert cache.get("order-missing") is None

    def test_put_duplicate_returns_false(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        cache.put_if_absent("order-1", {"order_id": "ord_1"})
        assert cache.put_if_absent("order-1", {"order_id": "ord_2"}) is False

    def test_delete_existing_returns_true(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        cache.put_if_absent("order-1", {"order_id": "ord_1"})
        assert cache.delete("order-1") is True
        assert cache.get("order-1") is None

    def test_delete_missing_returns_false(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        assert cache.delete("order-missing") is False

    def test_clear_removes_all(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        cache.put_if_absent("a", {"x": 1})
        cache.put_if_absent("b", {"y": 2})
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None

    def test_contains_operator(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        cache.put_if_absent("key-1", {"v": 1})
        assert "key-1" in cache
        assert "key-2" not in cache


# ── MemoryIdempotencyCache: TTL Expiry ────────────────────────────────────────


class TestMemoryIdempotencyCacheTTL:
    def test_ttl_expiry_removes_on_get(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache(default_ttl=1)
        cache.put_if_absent("exp-1", {"x": 1})
        time.sleep(1.2)
        assert cache.get("exp-1") is None

    def test_ttl_expiry_removes_on_contains(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache(default_ttl=1)
        cache.put_if_absent("exp-1", {"x": 1})
        time.sleep(1.2)
        assert "exp-1" not in cache

    def test_put_after_expiry_succeeds(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache(default_ttl=1)
        cache.put_if_absent("exp-1", {"x": 1})
        time.sleep(1.2)
        assert cache.put_if_absent("exp-1", {"x": 2}) is True

    def test_explicit_ttl_override(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache(default_ttl=3600)
        # Override default TTL with much shorter
        cache.put_if_absent("short", {"x": 1}, ttl=1)
        time.sleep(1.2)
        assert cache.get("short") is None

    def test_rejects_zero_or_negative_default_ttl(self) -> None:
        with pytest.raises(ValueError, match="default_ttl must be > 0"):
            MemoryIdempotencyCache(default_ttl=0)
        with pytest.raises(ValueError, match="default_ttl must be > 0"):
            MemoryIdempotencyCache(default_ttl=-1)

    def test_rejects_zero_or_negative_put_ttl(self) -> None:
        cache = MemoryIdempotencyCache()
        with pytest.raises(ValueError, match="ttl must be > 0"):
            cache.put_if_absent("k", {"x": 1}, ttl=0)
        with pytest.raises(ValueError, match="ttl must be > 0"):
            cache.put_if_absent("k", {"x": 1}, ttl=-1)


# ── MemoryIdempotencyCache: SHA-256 hashing isolation ─────────────────────────


class TestMemoryIdempotencyCacheHashing:
    def test_keys_with_collision_in_storage(self) -> None:
        """Different input keys map to different SHA-256 hashes; both stored."""
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        cache.put_if_absent("order-1", {"v": "a"})
        cache.put_if_absent("order-2", {"v": "b"})
        assert cache.get("order-1") == {"v": "a"}
        assert cache.get("order-2") == {"v": "b"}

    def test_unicode_keys_supported(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        cache.put_if_absent("निफ्टी", {"v": 1})
        assert cache.get("निफ्टी") == {"v": 1}


# ── MemoryIdempotencyCache: Thread safety ─────────────────────────────────────


class TestMemoryIdempotencyCacheConcurrency:
    def test_concurrent_puts_thread_safe(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        results: list[bool] = []
        lock = threading.Lock()

        def worker(i: int) -> None:
            stored = cache.put_if_absent(f"key-{i}", {"i": i})
            with lock:
                results.append(stored)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads: t.start()
        for t in threads: t.join()

        # All 50 unique keys should have stored successfully
        assert sum(results) == 50

    def test_concurrent_put_duplicates_only_one_stored(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        results: list[bool] = []
        lock = threading.Lock()

        def worker() -> None:
            stored = cache.put_if_absent("shared-key", {"v": 1})
            with lock:
                results.append(stored)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()

        # Exactly one True (winner), 19 False
        assert sum(results) == 1


# ── MemoryIdempotencyCache: stats() ───────────────────────────────────────────


class TestMemoryIdempotencyCacheStats:
    def test_stats_initial_zeros(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        stats = cache.stats()
        assert stats["size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["puts_stored"] == 0
        assert stats["puts_existed"] == 0
        assert stats["deletes"] == 0
        assert stats["backend"] == "memory"

    def test_stats_tracks_hits_misses(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        cache.put_if_absent("k", {"v": 1})
        cache.get("k")  # hit
        cache.get("missing")  # miss
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_stats_tracks_puts_stored_vs_existed(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        cache.put_if_absent("k", {"v": 1})  # stored
        cache.put_if_absent("k", {"v": 2})  # existed
        stats = cache.stats()
        assert stats["puts_stored"] == 1
        assert stats["puts_existed"] == 1

    def test_stats_tracks_deletes(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        cache.put_if_absent("k", {"v": 1})
        cache.delete("k")
        cache.delete("missing")
        stats = cache.stats()
        assert stats["deletes"] == 1


# ── Protocol conformance ──────────────────────────────────────────────────────


class TestProtocolConformance:
    def test_memory_cache_satisfies_protocol(self) -> None:
        cache: MemoryIdempotencyCache[dict[str, Any]] = MemoryIdempotencyCache()
        assert isinstance(cache, IdempotencyCacheProtocol)


# ── Redis fallback path ───────────────────────────────────────────────────────


class TestRedisIdempotencyCacheFallback:
    def test_missing_redis_package_falls_back_to_memory(self) -> None:
        """When `redis` import fails, __new__ returns MemoryIdempotencyCache."""
        import builtins

        real_import = builtins.__import__

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "redis" or name.startswith("redis."):
                raise ImportError("simulated missing redis package")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            cache = RedisIdempotencyCache[str](redis_url="redis://localhost:6379/0")
        assert isinstance(cache, MemoryIdempotencyCache)

    def test_unreachable_redis_falls_back_to_memory(self) -> None:
        """When redis package is installed but server isn't reachable, fall back."""
        mock_redis_module = MagicMock()
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.from_url.return_value = mock_client

        with patch.dict("sys.modules", {"redis": mock_redis_module}):
            # URL that we treat as 'unreachable' — but Ping returns True, so it'll use the redis path.
            # Instead use a FastAPI-like case: simulate ping raising an exception
            failing_mock = MagicMock()
            failing_mock.Redis.from_url.side_effect = ConnectionError("simulated unreachable")
            with patch.dict("sys.modules", {"redis": failing_mock}):
                cache = RedisIdempotencyCache[str](redis_url="redis://unreachable:6379/0")
        assert isinstance(cache, MemoryIdempotencyCache)


# ── IdempotencyStats and CacheEntry dataclasses ───────────────────────────────


class TestDataclasses:
    def test_idempotency_stats_as_dict_keys(self) -> None:
        s = IdempotencyStats(size=3, hits=2, misses=1, puts_stored=4, puts_existed=5, deletes=0, expired=1, backend="memory")
        d = s.as_dict()
        assert d == {
            "size": 3,
            "hits": 2,
            "misses": 1,
            "puts_stored": 4,
            "puts_existed": 5,
            "deletes": 0,
            "expired": 1,
            "backend": "memory",
        }

    def test_cache_entry_stores_serialised_json(self) -> None:
        entry = CacheEntry(value_json='{"a": 1}', expires_at=time.monotonic() + 100)
        assert entry.value_json == '{"a": 1}'
        assert entry.expires_at > time.monotonic()

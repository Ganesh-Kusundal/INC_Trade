"""Tests for the Redis cache backend."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.cache import Cache, MemoryCache

# ---------------------------------------------------------------------------
# Helpers – minimal mock that mimics redis.asyncio.Redis
# ---------------------------------------------------------------------------

class _FakeRedis:
    """In-memory mock of the subset of redis.asyncio.Redis we use."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._ttls: dict[str, int | None] = {}

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._store[key] = value
        self._ttls[key] = ex

    async def delete(self, *keys: str) -> int:
        count = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                self._ttls.pop(k, None)
                count += 1
        return count

    async def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    def scan_iter(self, pattern: str):  # type: ignore[no-untyped-def]
        """Async iterator over matching keys."""

        async def _iter():  # type: ignore[no-untyped-def]
            import fnmatch

            for k in list(self._store):
                if fnmatch.fnmatch(k, pattern):
                    yield k

        return _iter()

    async def aclose(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_redis() -> _FakeRedis:
    return _FakeRedis()


@pytest.fixture
def redis_cache(fake_redis: _FakeRedis):  # type: ignore[no-untyped-def]
    """Return a RedisCache wired to a _FakeRedis (no real Redis needed)."""
    import infrastructure.cache_redis as mod

    with patch.object(mod, "_REDIS_AVAILABLE", True):
        with patch("redis.asyncio.ConnectionPool") as mock_pool_cls:
            with patch("redis.asyncio.Redis") as mock_redis_cls:
                mock_pool_cls.from_url.return_value = MagicMock()
                mock_redis_cls.return_value = fake_redis
                from infrastructure.cache_redis import RedisCache

                cache = RedisCache(url="redis://localhost:6379/0")
                yield cache  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 1. RedisCache implements the Cache interface
# ---------------------------------------------------------------------------

class TestRedisCacheInterface:
    def test_is_subclass_of_cache(self) -> None:
        from infrastructure.cache_redis import RedisCache

        assert issubclass(RedisCache, Cache)

    def test_has_all_abstract_methods(self) -> None:
        from infrastructure.cache_redis import RedisCache

        for method in ("get", "set", "delete", "clear", "has"):
            assert hasattr(RedisCache, method)


# ---------------------------------------------------------------------------
# 2. Fallback to MemoryCache when redis is not installed
# ---------------------------------------------------------------------------

class TestFallback:
    def test_get_redis_cache_without_package(self) -> None:
        import infrastructure.cache_redis as mod

        with patch.object(mod, "_REDIS_AVAILABLE", False):
            with patch.dict("os.environ", {}, clear=True):
                from infrastructure.cache_redis import get_redis_cache

                cache = get_redis_cache()
                assert isinstance(cache, MemoryCache)

    def test_get_redis_cache_without_env_var(self) -> None:
        import infrastructure.cache_redis as mod

        with patch.object(mod, "_REDIS_AVAILABLE", True):
            with patch.dict("os.environ", {}, clear=True):
                from infrastructure.cache_redis import get_redis_cache

                cache = get_redis_cache()
                assert isinstance(cache, MemoryCache)

    def test_get_redis_cache_with_both(self) -> None:
        import infrastructure.cache_redis as mod
        from infrastructure.cache_redis import RedisCache

        with patch.object(mod, "_REDIS_AVAILABLE", True):
            with patch.dict("os.environ", {"REDIS_URL": "redis://localhost:6379"}):
                with patch("redis.asyncio.ConnectionPool") as mock_pool:
                    with patch("redis.asyncio.Redis"):
                        mock_pool.from_url.return_value = MagicMock()
                        from infrastructure.cache_redis import get_redis_cache

                        cache = get_redis_cache()
                        assert isinstance(cache, RedisCache)


# ---------------------------------------------------------------------------
# 3. JSON serialization roundtrip
# ---------------------------------------------------------------------------

class TestSerialization:
    @pytest.mark.asyncio
    async def test_json_roundtrip_dict(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        data = {"price": 100.5, "symbol": "INFY", "tags": ["a", "b"]}
        await redis_cache.aset("k1", data)
        result = await redis_cache.aget("k1")
        assert result == data

    @pytest.mark.asyncio
    async def test_json_roundtrip_list(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        data = [1, 2, 3, {"nested": True}]
        await redis_cache.aset("k2", data)
        result = await redis_cache.aget("k2")
        assert result == data

    @pytest.mark.asyncio
    async def test_json_roundtrip_string(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        await redis_cache.aset("k3", "hello")
        result = await redis_cache.aget("k3")
        assert result == "hello"

    @pytest.mark.asyncio
    async def test_json_roundtrip_none_value(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        await redis_cache.aset("k4", None)
        result = await redis_cache.aget("k4")
        # None serializes as "null" which json.loads returns as None
        assert result is None

    @pytest.mark.asyncio
    async def test_non_serializable_falls_back_to_str(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        import datetime

        val = datetime.datetime(2025, 1, 1)
        await redis_cache.aset("k5", val)
        result = await redis_cache.aget("k5")
        # str fallback: stored as str(datetime), returned as-is (not JSON)
        assert "2025-01-01" in str(result)

    @pytest.mark.asyncio
    async def test_missing_key_returns_none(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        result = await redis_cache.aget("nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# 4. TTL expiry
# ---------------------------------------------------------------------------

class TestTTL:
    @pytest.mark.asyncio
    async def test_key_expires_after_ttl(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        await redis_cache.aset("ttl_key", "value", ttl=1)
        # Immediately available
        assert await redis_cache.aget("ttl_key") == "value"
        # Simulate expiry by removing from fake store
        redis_cache._client._store.pop("tradexv2:ttl_key", None)
        assert await redis_cache.aget("ttl_key") is None

    @pytest.mark.asyncio
    async def test_default_ttl_applied(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        await redis_cache.aset("default_ttl_key", 42)
        ttl = redis_cache._client._ttls.get("tradexv2:default_ttl_key")
        assert ttl == 300  # default_ttl

    @pytest.mark.asyncio
    async def test_no_ttl_when_zero(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        await redis_cache.aset("no_ttl", "val", ttl=0)
        assert redis_cache._client._ttls.get("tradexv2:no_ttl") is None


# ---------------------------------------------------------------------------
# 5. Prefix namespacing
# ---------------------------------------------------------------------------

class TestPrefix:
    @pytest.mark.asyncio
    async def test_keys_prefixed(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        await redis_cache.aset("foo", "bar")
        assert "tradexv2:foo" in redis_cache._client._store

    @pytest.mark.asyncio
    async def test_custom_prefix(self, fake_redis: _FakeRedis) -> None:
        import infrastructure.cache_redis as mod

        with patch.object(mod, "_REDIS_AVAILABLE", True):
            with patch("redis.asyncio.ConnectionPool") as mock_pool_cls:
                with patch("redis.asyncio.Redis") as mock_redis_cls:
                    mock_pool_cls.from_url.return_value = MagicMock()
                    mock_redis_cls.return_value = fake_redis
                    from infrastructure.cache_redis import RedisCache

                    cache = RedisCache(url="redis://localhost:6379/0", prefix="myapp:")
                    await cache.aset("x", 1)
                    assert "myapp:x" in fake_redis._store


# ---------------------------------------------------------------------------
# 6. has / delete / clear
# ---------------------------------------------------------------------------

class TestOperations:
    @pytest.mark.asyncio
    async def test_has_returns_true_for_existing(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        await redis_cache.aset("h1", "v")
        assert await redis_cache.ahas("h1") is True

    @pytest.mark.asyncio
    async def test_has_returns_false_for_missing(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        assert await redis_cache.ahas("missing") is False

    @pytest.mark.asyncio
    async def test_delete_removes_key(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        await redis_cache.aset("d1", "v")
        await redis_cache.adelete("d1")
        assert await redis_cache.aget("d1") is None

    @pytest.mark.asyncio
    async def test_clear_removes_all_prefixed_keys(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        await redis_cache.aset("c1", 1)
        await redis_cache.aset("c2", 2)
        await redis_cache.aclear()
        assert await redis_cache.aget("c1") is None
        assert await redis_cache.aget("c2") is None


# ---------------------------------------------------------------------------
# 7. Sync bridge works
# ---------------------------------------------------------------------------

class TestSyncBridge:
    def test_sync_get_set(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        redis_cache.set("sync_key", {"a": 1})
        result = redis_cache.get("sync_key")
        assert result == {"a": 1}

    def test_sync_has(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        redis_cache.set("sync_has", "yes")
        assert redis_cache.has("sync_has") is True
        assert redis_cache.has("nope") is False

    def test_sync_delete(self, redis_cache: Any) -> None:  # type: ignore[no-untyped-def]
        redis_cache.set("sync_del", 1)
        redis_cache.delete("sync_del")
        assert redis_cache.get("sync_del") is None


# ---------------------------------------------------------------------------
# 8. Import guard
# ---------------------------------------------------------------------------

class TestImportGuard:
    def test_redis_cache_raises_without_package(self) -> None:
        import infrastructure.cache_redis as mod

        with patch.object(mod, "_REDIS_AVAILABLE", False):
            with pytest.raises(ImportError, match="redis"):
                mod.RedisCache()

"""Cross-broker idempotency cache — deduplicates order placements and WS fills."""

from __future__ import annotations
import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Generic, Optional, Protocol, TypeVar, runtime_checkable
from brokers.common.logging_helpers import log_warning as _log_warning


logger = logging.getLogger(__name__)

T = TypeVar("T")

@dataclass(frozen=True)
class IdempotencyResult:
    STORED: str = "stored"
    EXISTS: str = "exists"

@runtime_checkable
class IdempotencyCacheProtocol(Protocol[T]):
    def get(self, key: str) -> Optional[T]: ...
    def put_if_absent(self, key: str, value: T, ttl: int | None = None) -> bool: ...
    def delete(self, key: str) -> bool: ...
    def clear(self) -> None: ...
    def stats(self) -> dict[str, Any]: ...
    def __contains__(self, key: str) -> bool: ...

def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()

def _serialize(value: Any) -> str:
    return json.dumps(value, default=str)

def _deserialize(raw: str) -> Any:
    return json.loads(raw)

@dataclass
class CacheEntry:
    value_json: str
    expires_at: float

@dataclass
class IdempotencyStats:
    size: int = 0
    hits: int = 0
    misses: int = 0
    puts_stored: int = 0
    puts_existed: int = 0
    deletes: int = 0
    expired: int = 0
    backend: str = "memory"
    def as_dict(self) -> dict[str, Any]:
        return {"size": self.size, "hits": self.hits, "misses": self.misses, "puts_stored": self.puts_stored, "puts_existed": self.puts_existed, "deletes": self.deletes, "expired": self.expired, "backend": self.backend}

class MemoryIdempotencyCache(Generic[T]):
    def __init__(self, default_ttl: int = 3600) -> None:
        if default_ttl <= 0: raise ValueError("default_ttl must be > 0")
        self._lock = threading.RLock()
        self._store: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._stats = IdempotencyStats(backend="memory")
    def get(self, key: str) -> Optional[T]:
        h = _hash_key(key)
        with self._lock:
            entry = self._store.get(h)
            if entry is None:
                self._stats.misses += 1; return None
            if self._is_expired(entry):
                del self._store[h]; self._stats.expired += 1; self._stats.misses += 1; return None
            self._stats.hits += 1
            return _deserialize(entry.value_json)  # type: ignore[no-any-return]
    def put_if_absent(self, key: str, value: T, ttl: int | None = None) -> bool:
        h = _hash_key(key)
        effective_ttl = ttl if ttl is not None else self._default_ttl
        if effective_ttl <= 0: raise ValueError("ttl must be > 0")
        with self._lock:
            entry = self._store.get(h)
            if entry is not None and not self._is_expired(entry):
                self._stats.puts_existed += 1; return False
            self._store[h] = CacheEntry(value_json=_serialize(value), expires_at=time.monotonic() + effective_ttl)
            self._stats.puts_stored += 1; return True
    def delete(self, key: str) -> bool:
        h = _hash_key(key)
        with self._lock:
            if h in self._store:
                del self._store[h]; self._stats.deletes += 1; return True
            return False
    def clear(self) -> None:
        with self._lock:
            self._store.clear()
    def __contains__(self, key: str) -> bool:
        h = _hash_key(key)
        with self._lock:
            entry = self._store.get(h)
            if entry is None: return False
            if self._is_expired(entry):
                del self._store[h]; self._stats.expired += 1; return False
            return True
    def stats(self) -> dict[str, Any]:
        with self._lock:
            self._purge_expired(); self._stats.size = len(self._store); return self._stats.as_dict()
    def _is_expired(self, entry: CacheEntry) -> bool:
        return time.monotonic() >= entry.expires_at
    def _purge_expired(self) -> None:
        now = time.monotonic()
        expired = [h for h, e in self._store.items() if now >= e.expires_at]
        for h in expired:
            del self._store[h]; self._stats.expired += 1

class RedisIdempotencyCache(Generic[T]):
    def __new__(cls, redis_url: str = "redis://localhost:6379/0", default_ttl: int = 3600, **kwargs: Any) -> Any:
        try:
            import redis
            try:
                redis.Redis.from_url(redis_url).ping()
                inst = object.__new__(cls); inst.__init__(redis_url=redis_url, default_ttl=default_ttl, **kwargs); return inst  # type: ignore[misc]
            except Exception as exc:
                _log_warning("redis_unreachable_fallback_to_memory", error=str(exc)[:200])
                return MemoryIdempotencyCache(default_ttl=default_ttl)
        except ImportError:
            _log_warning("redis_package_missing_fallback_to_memory", redis_url=redis_url)
            return MemoryIdempotencyCache(default_ttl=default_ttl)
    def __init__(self, redis_url: str = "redis://localhost:6379/0", default_ttl: int = 3600, prefix: str = "idempotency:") -> None:
        if default_ttl <= 0: raise ValueError("default_ttl must be > 0")
        import redis as _redis
        self._url = redis_url; self._default_ttl = default_ttl; self._prefix = prefix
        self._client = _redis.Redis.from_url(redis_url, decode_responses=True)
        self._lock = threading.RLock(); self._stats = IdempotencyStats(backend="redis")
    def _k(self, key: str) -> str: return f"{self._prefix}{_hash_key(key)}"
    def get(self, key: str) -> Optional[T]:
        with self._lock:
            try:
                raw = self._client.get(self._k(key))
            except Exception as exc: _log_warning("redis_get_failed", error=str(exc)[:200]); return None
            if raw is None: self._stats.misses += 1; return None
            self._stats.hits += 1; return _deserialize(raw)  # type: ignore[no-any-return]
    def put_if_absent(self, key: str, value: T, ttl: int | None = None) -> bool:
        effective_ttl = ttl if ttl is not None else self._default_ttl
        if effective_ttl <= 0: raise ValueError("ttl must be > 0")
        with self._lock:
            try:
                stored = self._client.set(self._k(key), _serialize(value), nx=True, ex=effective_ttl)
            except Exception as exc: _log_warning("redis_set_failed", error=str(exc)[:200]); return False
            if stored: self._stats.puts_stored += 1; return True
            self._stats.puts_existed += 1; return False
    def delete(self, key: str) -> bool:
        with self._lock:
            try:
                deleted = self._client.delete(self._k(key))
            except Exception as exc: _log_warning("redis_delete_failed", error=str(exc)[:200]); return False
            if deleted: self._stats.deletes += 1; return True
            return False
    def clear(self) -> None:
        with self._lock:
            try:
                cursor = 0
                while True:
                    cursor, keys = self._client.scan(cursor=cursor, match=f"{self._prefix}*")
                    if keys: self._client.delete(*keys)
                    if cursor == 0: break
            except Exception as exc: _log_warning("redis_clear_failed", error=str(exc)[:200])
    def __contains__(self, key: str) -> bool:
        with self._lock:
            try: return self._client.exists(self._k(key)) > 0  # type: ignore[no-any-return]
            except Exception: return False
    def stats(self) -> dict[str, Any]:
        with self._lock: self._stats.backend = "redis"; return self._stats.as_dict()

__all__ = ["CacheEntry", "IdempotencyCacheProtocol", "IdempotencyResult", "IdempotencyStats", "MemoryIdempotencyCache", "RedisIdempotencyCache"]

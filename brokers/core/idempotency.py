import os
import json
import logging
import threading
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class IdempotencyCache:
    """
    Prevents duplicate execution of critical commands (like place_order) during network retries.
    Follows the fail-safe principles audited in Phase 5:
    Memory primary -> FileSystem fallback.

    Thread-safe via RLock. Supports TTL-based and LRU eviction.
    """

    def __init__(
        self,
        fallback_dir: str = ".cache/idempotency",
        ttl_seconds: float = 3600.0,
        max_size: int = 1000,
    ):
        self.fallback_dir = fallback_dir
        self._memory_cache: dict[str, float] = {}
        self._lock = threading.RLock()
        self._ttl = ttl_seconds
        self._max_size = max_size
        if not os.path.exists(self.fallback_dir):
            os.makedirs(self.fallback_dir, exist_ok=True)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, ts in self._memory_cache.items() if now - ts > self._ttl]
        for key in expired:
            del self._memory_cache[key]

    def _evict_lru(self) -> None:
        while len(self._memory_cache) > self._max_size:
            oldest_key = min(self._memory_cache, key=lambda k: self._memory_cache[k])
            del self._memory_cache[oldest_key]

    def check_and_set(self, correlation_id: str) -> bool:
        """
        Returns True if the ID was successfully set (first time seen).
        Returns False if the ID already exists (duplicate detected).
        """
        with self._lock:
            self._evict_expired()

            if correlation_id in self._memory_cache:
                logger.warning(
                    f"Idempotency hit (Memory): {correlation_id}. Duplicate request blocked."
                )
                return False

            file_path = os.path.join(self.fallback_dir, f"{correlation_id}.json")
            if os.path.exists(file_path):
                logger.warning(
                    f"Idempotency hit (FileSystem): {correlation_id}. Duplicate request blocked."
                )
                return False

            self._memory_cache[correlation_id] = time.monotonic()
            self._evict_lru()

            try:
                with open(file_path, "w") as f:
                    json.dump({"timestamp": datetime.now(timezone.utc).isoformat()}, f)
            except Exception as e:
                logger.error(
                    f"Failed to write idempotency fallback for {correlation_id}: {e}"
                )

            return True

    def remove(self, correlation_id: str):
        with self._lock:
            self._memory_cache.pop(correlation_id, None)

            file_path = os.path.join(self.fallback_dir, f"{correlation_id}.json")
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass

    def lock(self, key: str):
        """Context manager for atomic check-then-act on a given key."""
        return _IdempotencyLock(self, key)


class _IdempotencyLock:
    def __init__(self, cache: IdempotencyCache, key: str):
        self._cache = cache
        self._key = key
        self._result = False

    def __enter__(self) -> "_IdempotencyLock":
        self._cache._lock.acquire()
        self._result = self._key not in self._cache._memory_cache
        if self._result:
            self._cache._memory_cache[self._key] = time.monotonic()
        return self

    def __exit__(self, *args):
        self._cache._lock.release()

    @property
    def acquired(self) -> bool:
        return self._result

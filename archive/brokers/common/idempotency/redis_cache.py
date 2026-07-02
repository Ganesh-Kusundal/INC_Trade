"""Redis-based idempotency cache for production deployments.

This implementation uses Redis as a distributed cache backend, providing:
- Cross-process and cross-machine idempotency
- Automatic TTL-based expiration
- High availability and scalability
- Distributed locking support
- Atomic operations

For development and single-instance deployments, use MemoryIdempotencyCache instead.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Generic, TypeVar

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None  # type: ignore

from brokers.common.idempotency.service import IdempotencyCacheBackend
from brokers.common.idempotency.exceptions import (
    IdempotencyCacheError,
    IdempotencyTimeoutError,
    DistributedLockError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RedisIdempotencyCache(IdempotencyCacheBackend[T]):
    """Redis-based distributed idempotency cache.
    
    This cache uses Redis for distributed caching across multiple processes and machines.
    It supports automatic TTL expiration and distributed locking.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        default_ttl_seconds: int = 86400,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        lock_timeout: float = 10.0,
        lock_retry_interval: float = 0.1,
        max_lock_retries: int = 50,
    ):
        """Initialize the Redis cache.
        
        Args:
            host: Redis server host
            port: Redis server port
            db: Redis database number
            password: Redis password (optional)
            default_ttl_seconds: Default TTL for entries in seconds
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Connection timeout in seconds
            lock_timeout: Lock acquisition timeout in seconds
            lock_retry_interval: Time between lock acquisition retries
            max_lock_retries: Maximum number of lock acquisition retries
        """
        if not REDIS_AVAILABLE:
            raise ImportError(
                "Redis package is not available. Install with: pip install redis"
            )
        
        self._host = host
        self._port = port
        self._db = db
        self._password = password
        self._default_ttl = default_ttl_seconds
        self._socket_timeout = socket_timeout
        self._connect_timeout = socket_connect_timeout
        self._lock_timeout = lock_timeout
        self._lock_retry_interval = lock_retry_interval
        self._max_lock_retries = max_lock_retries
        
        # Connection pool configuration
        self._connection_pool = None
        self._redis_client = None
        self._lock = threading.RLock()
        
        # Metrics
        self._hits = 0
        self._misses = 0
        self._timeouts = 0
        self._connection_errors = 0
        
        # Initialize connection
        self._connect()

    def _connect(self) -> None:
        """Establish connection to Redis server."""
        with self._lock:
            try:
                # Create connection pool
                self._connection_pool = redis.ConnectionPool(
                    host=self._host,
                    port=self._port,
                    db=self._db,
                    password=self._password,
                    socket_timeout=self._socket_timeout,
                    socket_connect_timeout=self._connect_timeout,
                    health_check_interval=30,
                )
                
                # Create client
                self._redis_client = redis.Redis(
                    connection_pool=self._connection_pool,
                    socket_timeout=self._socket_timeout,
                    socket_connect_timeout=self._connect_timeout,
                )
                
                # Test connection
                self._redis_client.ping()
                logger.info(f"Connected to Redis at {self._host}:{self._port}/db{self._db}")
                
            except redis.RedisError as exc:
                logger.error(f"Failed to connect to Redis: {exc}")
                self._connection_pool = None
                self._redis_client = None
                raise IdempotencyCacheError(f"Redis connection failed: {exc}", "redis")

    def _get_client(self) -> redis.Redis:
        """Get Redis client, reconnecting if necessary."""
        if self._redis_client is None:
            self._connect()
        return self._redis_client  # type: ignore

    def _serialize_value(self, value: T) -> str:
        """Serialize a value for Redis storage."""
        try:
            if isinstance(value, str):
                return value
            return json.dumps(value, default=str)
        except (TypeError, ValueError) as exc:
            logger.error(f"Failed to serialize value for Redis: {exc}")
            raise IdempotencyCacheError(f"Value serialization failed: {exc}", "redis")

    def _deserialize_value(self, serialized: str | bytes | None, expected_type: type | None = None) -> T | None:
        """Deserialize a value from Redis storage."""
        if serialized is None:
            return None
        
        try:
            if isinstance(serialized, bytes):
                serialized = serialized.decode('utf-8')
            
            if isinstance(serialized, str):
                # Try to deserialize as JSON, fall back to raw string
                try:
                    return json.loads(serialized)  # type: ignore
                except json.JSONDecodeError:
                    return serialized  # type: ignore
            
            return serialized  # type: ignore
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            logger.error(f"Failed to deserialize value from Redis: {exc}")
            raise IdempotencyCacheError(f"Value deserialization failed: {exc}", "redis")

    def _acquire_lock(self, key: str, timeout: float | None = None) -> bool:
        """Acquire a distributed lock for a key."""
        client = self._get_client()
        lock_timeout = timeout if timeout is not None else self._lock_timeout
        lock_name = f"idempotency_lock:{key}"
        
        try:
            # Use Redis SET with NX and PX options for atomic lock acquisition
            # Returns True if lock was acquired, False otherwise
            acquired = client.set(
                lock_name,
                "locked",
                nx=True,
                px=int(lock_timeout * 1000)  # Convert to milliseconds
            )
            return bool(acquired)
        except redis.RedisError as exc:
            logger.error(f"Failed to acquire lock for {key}: {exc}")
            raise DistributedLockError(f"Lock acquisition failed: {exc}", key, lock_name)

    def _release_lock(self, key: str) -> bool:
        """Release a distributed lock for a key."""
        client = self._get_client()
        lock_name = f"idempotency_lock:{key}"
        
        try:
            # Use LUA script for atomic unlock
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            result = client.eval(lua_script, 1, lock_name, "locked")
            return bool(result)
        except redis.RedisError as exc:
            logger.error(f"Failed to release lock for {key}: {exc}")
            # Try simple delete as fallback
            try:
                client.delete(lock_name)
                return True
            except redis.RedisError:
                return False

    def _with_lock(self, key: str, func, *args, **kwargs):
        """Execute a function with distributed locking."""
        lock_name = f"idempotency_lock:{key}"
        
        for attempt in range(self._max_lock_retries):
            try:
                # Try to acquire lock
                if self._acquire_lock(key):
                    try:
                        return func(*args, **kwargs)
                    finally:
                        self._release_lock(key)
                else:
                    # Lock not acquired, wait and retry
                    time.sleep(self._lock_retry_interval)
            except DistributedLockError:
                time.sleep(self._lock_retry_interval)
        
        raise IdempotencyTimeoutError(
            f"Failed to acquire lock after {self._max_lock_retries} attempts",
            key,
            self._lock_timeout
        )

    def get(self, key: str) -> T | None:
        """Retrieve a value by key from Redis."""
        client = self._get_client()
        cache_key = f"idempotency:{key}"
        
        try:
            serialized = client.get(cache_key)
            if serialized is None:
                self._misses += 1
                return None
            
            value = self._deserialize_value(serialized)
            self._hits += 1
            return value
            
        except redis.RedisError as exc:
            self._connection_errors += 1
            logger.error(f"Redis get failed for {key}: {exc}")
            return None

    def put(self, key: str, value: T, ttl_seconds: int | None = None) -> None:
        """Store a value by key in Redis with optional TTL."""
        client = self._get_client()
        cache_key = f"idempotency:{key}"
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        
        try:
            serialized = self._serialize_value(value)
            if ttl > 0:
                client.setex(cache_key, ttl, serialized)
            else:
                client.set(cache_key, serialized)
        except redis.RedisError as exc:
            self._connection_errors += 1
            logger.error(f"Redis put failed for {key}: {exc}")
            raise IdempotencyCacheError(f"Redis put failed: {exc}", "redis", key)

    def delete(self, key: str) -> bool:
        """Delete a value by key from Redis."""
        client = self._get_client()
        cache_key = f"idempotency:{key}"
        
        try:
            result = client.delete(cache_key)
            return result > 0
        except redis.RedisError as exc:
            self._connection_errors += 1
            logger.error(f"Redis delete failed for {key}: {exc}")
            return False

    def clear(self) -> int:
        """Clear all idempotency entries from Redis."""
        client = self._get_client()
        
        try:
            # Use SCAN to find all idempotency keys and delete them
            # This is safer than FLUSHDB which would clear everything
            cursor = 0
            deleted_count = 0
            pattern = "idempotency:*"
            
            while True:
                cursor, keys = client.scan(cursor, match=pattern, count=100)
                if keys:
                    deleted_count += client.delete(*keys)
                if cursor == 0:
                    break
            
            return deleted_count
            
        except redis.RedisError as exc:
            self._connection_errors += 1
            logger.error(f"Redis clear failed: {exc}")
            return 0

    def contains(self, key: str) -> bool:
        """Check if a key exists in Redis."""
        client = self._get_client()
        cache_key = f"idempotency:{key}"
        
        try:
            return client.exists(cache_key) > 0
        except redis.RedisError as exc:
            self._connection_errors += 1
            logger.error(f"Redis contains check failed for {key}: {exc}")
            return False

    def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            client = self._get_client()
            return client.ping()
        except (redis.RedisError, AttributeError):
            return False

    def cleanup_expired(self) -> int:
        """Clean up expired entries. Redis handles this automatically, so this is a no-op."""
        # Redis automatically removes expired keys, so we just return 0
        # but we can optionally trigger manual cleanup
        try:
            client = self._get_client()
            # This is a no-op for Redis as it handles TTL automatically
            return 0
        except redis.RedisError:
            return 0

    def get_info(self) -> dict[str, Any]:
        """Get Redis cache information and statistics."""
        try:
            client = self._get_client()
            info = client.info("memory", "stats")
            
            return {
                "type": "redis",
                "host": self._host,
                "port": self._port,
                "db": self._db,
                "default_ttl_seconds": self._default_ttl,
                "connected": self.health_check(),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0.0,
                "connection_errors": self._connection_errors,
                "redis_info": {
                    "used_memory": info.get("used_memory_human", "unknown"),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0),
                }
            }
        except redis.RedisError as exc:
            return {
                "type": "redis",
                "host": self._host,
                "port": self._port,
                "connected": False,
                "error": str(exc),
                "hits": self._hits,
                "misses": self._misses,
                "connection_errors": self._connection_errors,
            }

    def reset_metrics(self) -> None:
        """Reset cache metrics."""
        with self._lock:
            self._hits = 0
            self._misses = 0
            self._connection_errors = 0
            self._timeouts = 0

    def close(self) -> None:
        """Close the Redis connection."""
        with self._lock:
            if self._redis_client is not None:
                try:
                    self._redis_client.close()
                except redis.RedisError:
                    pass
                self._redis_client = None
            
            if self._connection_pool is not None:
                try:
                    self._connection_pool.close()
                except Exception:
                    pass
                self._connection_pool = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def __del__(self):
        """Destructor - ensure connection is closed."""
        self.close()


class RedisIdempotencyCacheWithLocking(RedisIdempotencyCache[T]):
    """Redis idempotency cache with automatic distributed locking.
    
    This variant automatically acquires distributed locks for all operations
    to ensure atomicity in concurrent scenarios.
    """

    def get(self, key: str) -> T | None:
        """Retrieve a value with locking."""
        def _get():
            return super().get(key)
        return self._with_lock(key, _get)

    def put(self, key: str, value: T, ttl_seconds: int | None = None) -> None:
        """Store a value with locking."""
        def _put():
            super().put(key, value, ttl_seconds)
        self._with_lock(key, _put)

    def delete(self, key: str) -> bool:
        """Delete a value with locking."""
        def _delete():
            return super().delete(key)
        return self._with_lock(key, _delete)

    def contains(self, key: str) -> bool:
        """Check if key exists with locking."""
        def _contains():
            return super().contains(key)
        return self._with_lock(key, _contains)


__all__ = ["RedisIdempotencyCache", "RedisIdempotencyCacheWithLocking"]
"""Idempotency module for broker operations.

This module provides durable idempotency caching to prevent duplicate order placement
and other operations across process restarts and multiple instances.

Components:
- IdempotencyService: Main interface for idempotency operations
- RedisIdempotencyCache: Primary implementation using Redis (production)
- FileIdempotencyCache: Fallback implementation using file system
- MemoryIdempotencyCache: In-memory implementation (development/testing)

Usage:
    from brokers.common.idempotency import IdempotencyService, RedisIdempotencyCache
    
    # Production (with Redis)
    cache = RedisIdempotencyCache(host='localhost', port=6379)
    service = IdempotencyService(cache)
    
    # Development (in-memory)
    cache = MemoryIdempotencyCache()
    service = IdempotencyService(cache)
"""

from brokers.common.idempotency.service import IdempotencyService
from brokers.common.idempotency.redis_cache import RedisIdempotencyCache
from brokers.common.idempotency.file_cache import FileIdempotencyCache
from brokers.common.idempotency.memory_cache import MemoryIdempotencyCache

__all__ = [
    "IdempotencyService",
    "RedisIdempotencyCache", 
    "FileIdempotencyCache",
    "MemoryIdempotencyCache",
]
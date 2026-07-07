"""Repository framework — generic data access abstraction.

Provides a base repository pattern for caching and retrieving
domain objects. Providers implement concrete repositories for
their broker-specific data sources.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

from tradex.core.cache import TTLCache

K = TypeVar("K")
V = TypeVar("V")


class Repository(ABC, Generic[K, V]):
    """Abstract base repository for domain object storage.

    Defines the contract for data access layers. Concrete
    implementations handle broker-specific storage (in-memory,
    file-based, Redis, database, etc.).

    Type Parameters:
        K: Key type (e.g., str for order_id, int for security_id).
        V: Value type (e.g., Order, Quote, Instrument).
    """

    @abstractmethod
    async def get(self, key: K) -> Optional[V]:
        """Retrieve an entity by key. Returns None if not found."""

    @abstractmethod
    async def put(self, key: K, value: V) -> None:
        """Store an entity."""

    @abstractmethod
    async def remove(self, key: K) -> bool:
        """Remove an entity. Returns True if it existed."""

    @abstractmethod
    async def exists(self, key: K) -> bool:
        """Check if an entity exists."""

    @abstractmethod
    async def clear(self) -> None:
        """Remove all entities."""

    @abstractmethod
    async def size(self) -> int:
        """Return the number of stored entities."""


class InMemoryRepository(Repository[K, V]):
    """In-memory repository backed by TTLCache.

    Suitable for caching broker responses with automatic expiry.
    Thread-safe via asyncio locks in TTLCache.
    """

    def __init__(self, max_size: int = 10000, default_ttl: float = 60.0) -> None:
        self._cache = TTLCache[K, V](max_size=max_size, default_ttl=default_ttl)

    async def get(self, key: K) -> Optional[V]:
        return await self._cache.get(key)

    async def put(self, key: K, value: V) -> None:
        await self._cache.put(key, value)

    async def remove(self, key: K) -> bool:
        return await self._cache.invalidate(key)

    async def exists(self, key: K) -> bool:
        return await self._cache.get(key) is not None

    async def clear(self) -> None:
        await self._cache.clear()

    async def size(self) -> int:
        return await self._cache.size()


class CompositeRepository(Repository[K, V]):
    """Multi-tier repository with primary and fallback.

    Reads check primary first, then fallback.
    Writes go to both tiers.
    """

    def __init__(
        self,
        primary: Repository[K, V],
        fallback: Optional[Repository[K, V]] = None,
    ) -> None:
        self._primary = primary
        self._fallback = fallback

    async def get(self, key: K) -> Optional[V]:
        value = await self._primary.get(key)
        if value is not None:
            return value
        if self._fallback:
            value = await self._fallback.get(key)
            if value is not None:
                await self._primary.put(key, value)
        return value

    async def put(self, key: K, value: V) -> None:
        await self._primary.put(key, value)
        if self._fallback:
            await self._fallback.put(key, value)

    async def remove(self, key: K) -> bool:
        result = await self._primary.remove(key)
        if self._fallback:
            await self._fallback.remove(key)
        return result

    async def exists(self, key: K) -> bool:
        if await self._primary.exists(key):
            return True
        if self._fallback:
            return await self._fallback.exists(key)
        return False

    async def clear(self) -> None:
        await self._primary.clear()
        if self._fallback:
            await self._fallback.clear()

    async def size(self) -> int:
        return await self._primary.size()

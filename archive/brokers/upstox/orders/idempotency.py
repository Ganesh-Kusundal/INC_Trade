"""In-memory idempotency cache for order placement safety.

Now delegates to ``brokers.common.idempotency.simple_cache.SimpleIdempotencyCache``
(REF-02 deduplication).
"""

from typing import Generic, TypeVar

from brokers.common.idempotency.simple_cache import SimpleIdempotencyCache

T = TypeVar("T")


class InMemoryIdempotencyCache(SimpleIdempotencyCache[T]):
    """Backward-compatible alias for Upstox's idempotency cache.

    Subclasses ``SimpleIdempotencyCache`` with default settings
    (max_size=1000, ttl_seconds=3600).  All existing import paths
    and type references continue to work.
    """

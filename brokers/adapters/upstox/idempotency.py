"""Backward-compatible alias — use brokers.core.order_result_cache."""

from brokers.core.order_result_cache import OrderResultCache, TypedIdempotencyCache

InMemoryIdempotencyCache = OrderResultCache = TypedIdempotencyCache

__all__ = ["InMemoryIdempotencyCache", "OrderResultCache", "TypedIdempotencyCache"]

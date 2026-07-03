"""Backward-compatible alias — use brokers.core.order_result_cache."""

from brokers.core.order_result_cache import OrderResultCache, TypedIdempotencyCache

DhanIdempotencyCache = OrderResultCache = TypedIdempotencyCache

__all__ = ["DhanIdempotencyCache", "OrderResultCache", "TypedIdempotencyCache"]

"""Strangler bridge — canonical idempotency cache from brokers_core."""

from brokers_core.utils.idempotency_cache import TypedIdempotencyCache

IdempotencyCache = TypedIdempotencyCache

__all__ = ["IdempotencyCache", "TypedIdempotencyCache"]

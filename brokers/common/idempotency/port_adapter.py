"""Bridge durable idempotency backends to broker order-placement ports."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Generic, TypeVar

from brokers.common.gateway_interfaces import IdempotencyCachePort
from brokers.common.idempotency.codec import decode_idempotency_payload, encode_idempotency_value
from brokers.common.idempotency.file_cache import FileIdempotencyCache
from brokers.common.idempotency.service import IdempotencyCacheBackend, IdempotencyService

T = TypeVar("T")


class _DictCodecBackend(IdempotencyCacheBackend[dict]):
    """Wrap a dict-valued backend with typed encode/decode."""

    def __init__(self, backend: IdempotencyCacheBackend[dict]) -> None:
        self._backend = backend

    def get(self, key: str) -> dict | None:
        return self._backend.get(key)

    def put(self, key: str, value: dict, ttl_seconds: int | None = None) -> None:
        self._backend.put(key, value, ttl_seconds=ttl_seconds)

    def delete(self, key: str) -> bool:
        return self._backend.delete(key)

    def clear(self) -> int:
        return self._backend.clear()

    def contains(self, key: str) -> bool:
        return self._backend.contains(key)

    def health_check(self) -> bool:
        return self._backend.health_check()

    def cleanup_expired(self) -> int:
        return self._backend.cleanup_expired()


class DurableIdempotencyCache(Generic[T]):
    """File-backed idempotency cache with in-process locking for check-then-act."""

    def __init__(
        self,
        *,
        storage_dir: str | Path,
        default_ttl_seconds: int = 3600,
        value_type: type[T],
    ) -> None:
        self._value_type = value_type
        file_backend = FileIdempotencyCache[dict](
            storage_dir=str(storage_dir),
            default_ttl_seconds=default_ttl_seconds,
            use_locking=True,
        )
        self._service = IdempotencyService(
            _DictCodecBackend(file_backend),
            default_ttl_seconds=default_ttl_seconds,
            enable_fallback=False,
        )
        self._lock = threading.RLock()
        self._default_ttl = default_ttl_seconds

    @contextmanager
    def lock(self, _key: str):
        with self._lock:
            yield self

    def get(self, key: str) -> T | None:
        payload = self._service.get(key)
        if payload is None:
            return None
        value = decode_idempotency_payload(payload)
        if not isinstance(value, self._value_type):
            return None
        return value

    def put(self, key: str, value: T) -> None:
        payload = encode_idempotency_value(value)  # type: ignore[arg-type]
        self._service.put(key, payload, ttl_seconds=self._default_ttl)


class OrderIdempotencyCache(DurableIdempotencyCache["Order"]):
    """Durable idempotency cache for Dhan ``Order`` responses."""

    def __init__(self, *, storage_dir: str | Path, default_ttl_seconds: int = 3600) -> None:
        from domain import Order

        super().__init__(
            storage_dir=storage_dir,
            default_ttl_seconds=default_ttl_seconds,
            value_type=Order,
        )


class OrderResponseIdempotencyCache(DurableIdempotencyCache["OrderResponse"], IdempotencyCachePort):
    """Durable idempotency cache for Upstox ``OrderResponse`` values."""

    def __init__(self, *, storage_dir: str | Path, default_ttl_seconds: int = 3600) -> None:
        from domain import OrderResponse

        super().__init__(
            storage_dir=storage_dir,
            default_ttl_seconds=default_ttl_seconds,
            value_type=OrderResponse,
        )


def default_idempotency_dir(broker_id: str) -> Path:
    root = Path.home() / ".tradexv2" / "idempotency" / broker_id
    root.mkdir(parents=True, exist_ok=True)
    return root


def create_dhan_idempotency_cache(
    *,
    storage_dir: str | Path | None = None,
    default_ttl_seconds: int = 3600,
) -> OrderIdempotencyCache:
    return OrderIdempotencyCache(
        storage_dir=storage_dir or default_idempotency_dir("dhan"),
        default_ttl_seconds=default_ttl_seconds,
    )


def create_upstox_idempotency_cache(
    *,
    storage_dir: str | Path | None = None,
    default_ttl_seconds: int = 3600,
) -> OrderResponseIdempotencyCache:
    return OrderResponseIdempotencyCache(
        storage_dir=storage_dir or default_idempotency_dir("upstox"),
        default_ttl_seconds=default_ttl_seconds,
    )

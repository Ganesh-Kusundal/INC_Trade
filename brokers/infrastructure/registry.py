"""Singleton Gateway Registry to prevent duplicate gateways.

Also provides :class:`BrokerRegistry` (thread-safe registry of broker
gateways with health tracking) and :class:`ServiceRegistry` (generic
factory-based service container).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class GatewayRegistry:
    """Thread-safe singleton registry for broker gateways."""

    _instances: dict[str, Any] = {}
    _lock = threading.Lock()

    @classmethod
    def get_or_create(
        cls, broker_id: str, client_id: str, factory_fn: Callable[[], Any]
    ) -> Any:
        """Get existing gateway or create a new one using factory_fn."""
        key = f"{broker_id}:{client_id}"

        with cls._lock:
            if key in cls._instances:
                logger.debug(f"registry_hit for {key}")
                return cls._instances[key]

            logger.info(f"registry_miss creating new gateway for {key}")
            instance = factory_fn()
            cls._instances[key] = instance
            return instance

    @classmethod
    def clear(cls) -> None:
        with cls._lock:
            cls._instances.clear()


# ── Service Registry ────────────────────────────────────────────────────────


@dataclass
class _RegistryEntry(Generic[_T]):
    """Internal: a single service registration entry."""

    __slots__ = ("attr_name", "factory", "args", "kwargs")

    attr_name: str
    factory: type[_T]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


class ServiceRegistry(Generic[_T]):
    """Generic registry for constructing and storing service instances.

    Each entry specifies an attribute name, a factory class, positional
    args, keyword args, and optional extra kwargs passed to the factory.
    On ``instantiate_all()``, each factory is called with its arguments
    and the result is stored for later retrieval.
    """

    def __init__(self) -> None:
        self._entries: list[_RegistryEntry[_T]] = []
        self._instances: dict[str, _T] = {}

    def register(
        self,
        attr_name: str,
        factory: type[_T],
        *args: Any,
        extra: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        merged_kwargs = {**kwargs, **(extra or {})}
        self._entries.append(
            _RegistryEntry(
                attr_name=attr_name,
                factory=factory,
                args=args,
                kwargs=merged_kwargs,
            )
        )

    def instantiate_all(self) -> dict[str, _T]:
        for entry in self._entries:
            instance = entry.factory(*entry.args, **entry.kwargs)
            self._instances[entry.attr_name] = instance
        return dict(self._instances)

    def get(self, attr_name: str) -> _T | None:
        return self._instances.get(attr_name)

    def get_all(self) -> dict[str, _T]:
        return dict(self._instances)

    def __contains__(self, attr_name: str) -> bool:
        return attr_name in self._instances


# ── Broker Registry ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BrokerHealthSnapshot:
    """Point-in-time health state for a broker."""

    broker_id: str
    alive: bool
    reason: str = ""
    latency_ms: float = 0.0


class BrokerRegistry:
    """Thread-safe registry of broker gateways with health tracking.

    Lifecycle:
    1. At bootstrap, call ``register()`` for each available broker.
    2. The router reads health via ``get_health()`` on each routing decision.
    3. Health monitors call ``update_health()`` periodically.
    4. On shutdown, call ``close_all()``.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._gateways: dict[str, Any] = {}
        self._health: dict[str, BrokerHealthSnapshot] = {}
        self._metadata: dict[str, dict[str, Any]] = {}

    def register(
        self,
        broker_id: str,
        gateway: Any,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Register a broker gateway."""
        with self._lock:
            self._gateways[broker_id] = gateway
            self._health[broker_id] = BrokerHealthSnapshot(
                broker_id=broker_id, alive=True
            )
            if metadata:
                self._metadata[broker_id] = metadata
        logger.info("broker.registered: %s", broker_id)

    def deregister(self, broker_id: str) -> None:
        """Remove a broker from the registry."""
        with self._lock:
            self._gateways.pop(broker_id, None)
            self._health.pop(broker_id, None)
            self._metadata.pop(broker_id, None)
        logger.warning("broker.deregistered: %s", broker_id)

    def get_gateway(self, broker_id: str) -> Any:
        """Return the gateway for the given broker_id.

        Raises ``KeyError`` if not registered.
        """
        with self._lock:
            gw = self._gateways.get(broker_id)
        if gw is None:
            raise KeyError(f"Broker '{broker_id}' not registered")
        return gw

    def get_health(self, broker_id: str) -> BrokerHealthSnapshot:
        with self._lock:
            return self._health.get(
                broker_id,
                BrokerHealthSnapshot(broker_id=broker_id, alive=False, reason="not registered"),
            )

    def update_health(self, snapshot: BrokerHealthSnapshot) -> None:
        with self._lock:
            if snapshot.broker_id in self._gateways:
                self._health[snapshot.broker_id] = snapshot

    def list_brokers(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._gateways.keys())

    def has(self, broker_id: str) -> bool:
        with self._lock:
            return broker_id in self._gateways

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "broker_ids": tuple(self._gateways.keys()),
                "health": dict(self._health),
            }

    async def close_all(self) -> None:
        """Gracefully close all registered gateways."""
        with self._lock:
            gateways = list(self._gateways.values())
            ids = list(self._gateways.keys())
        for broker_id, gw in zip(ids, gateways):
            try:
                close_fn = getattr(gw, "close", None)
                if close_fn is not None:
                    result = close_fn()
                    if hasattr(result, "__await__"):
                        await result
            except Exception:
                logger.exception("broker.close.error: %s", broker_id)

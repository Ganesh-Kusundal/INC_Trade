"""ServiceRegistry — generic adapter/service registry for broker connections.

Both ``DhanConnection`` (``brokers/dhan/connection.py``) and
``UpstoxBrokerBuilder`` (``brokers/upstox/broker.py``) implement the
same pattern: a list of ``(attr_name, adapter_class)`` tuples that are
iterated in ``__init__`` to construct and set adapters dynamically.

This module provides a canonical ``ServiceRegistry`` that both brokers
can use instead of maintaining their own ad-hoc registry lists.

Usage
-----
    registry = ServiceRegistry()
    registry.register("market_data", MarketDataAdapter, client=client, resolver=resolver)
    registry.register("orders", OrdersAdapter, client=client)

    # Bulk instantiation
    registry.instantiate_all()

    # Or with extra kwargs per entry
    registry.register("orders", OrdersAdapter, extra={"allow_live_orders": True})

    # Attribute access
    gateway = registry.get("gateway")
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

_T = TypeVar("_T")


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
        """Register a service to be constructed.

        Parameters
        ----------
        attr_name : str
            Attribute name under which the instance will be stored.
        factory : type[_T]
            Class (or callable) that produces the instance.
        *args
            Positional arguments passed to the factory.
        extra : dict, optional
            Additional keyword arguments merged with **kwargs.
        **kwargs
            Keyword arguments passed to the factory.
        """
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
        """Construct all registered services.

        Returns a dict mapping attr_name → instance.
        """
        for entry in self._entries:
            instance = entry.factory(*entry.args, **entry.kwargs)
            self._instances[entry.attr_name] = instance
        return dict(self._instances)

    def get(self, attr_name: str) -> _T | None:
        """Retrieve a previously-constructed instance by its attribute name."""
        return self._instances.get(attr_name)

    def get_all(self) -> dict[str, _T]:
        """Return all constructed instances."""
        return dict(self._instances)

    def __contains__(self, attr_name: str) -> bool:
        return attr_name in self._instances


class _RegistryEntry(Generic[_T]):
    """Internal: a single service registration entry."""

    __slots__ = ("attr_name", "factory", "args", "kwargs")

    def __init__(
        self,
        attr_name: str,
        factory: type[_T],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        self.attr_name = attr_name
        self.factory = factory
        self.args = args
        self.kwargs = kwargs

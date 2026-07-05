"""Extension registry — type-safe extension discovery.

Architecture:
    ``ExtensionRegistryPort`` is a ``@runtime_checkable`` Protocol (port).
    ``DictExtensionRegistry`` is the concrete implementation (adapter).
    This follows the Dependency Inversion Principle — services depend on
    the Protocol, never on the concrete implementation.
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class ExtensionRegistryPort(Protocol):
    """Protocol for type-safe extension discovery.

    Replaces ``hasattr``-based capability detection with explicit typed
    registrations.  Brokers register typed extension instances at bootstrap
    time; callers use ``resolve()`` to obtain them by type.

    Usage::

        registry: ExtensionRegistryPort = DictExtensionRegistry()
        registry.register("dhan", MarginProvider, DhanMargin(client))

        if registry.supports("dhan", MarginProvider):
            margin = registry.resolve("dhan", MarginProvider)
            result = margin.calculate_margin(...)
    """

    def register(self, broker_id: str, extension_type: type[T], instance: T) -> None:
        """Register an extension for a broker."""
        ...

    def resolve(self, broker_id: str, extension_type: type[T]) -> T | None:
        """Get an extension, or ``None`` if not registered."""
        ...

    def supports(self, broker_id: str, extension_type: type[T]) -> bool:
        """Check if a broker supports a specific extension type."""
        ...


class DictExtensionRegistry:
    """Concrete extension registry backed by an in-memory dict-of-dicts.

    Implements ``ExtensionRegistryPort``.  Thread-safety is the caller's
    responsibility (typically ensured at bootstrap time, before any
    concurrent access).
    """

    def __init__(self) -> None:
        self._extensions: dict[str, dict[type, object]] = {}

    def register(self, broker_id: str, extension_type: type[T], instance: T) -> None:
        """Register an extension for a broker."""
        if broker_id not in self._extensions:
            self._extensions[broker_id] = {}
        self._extensions[broker_id][extension_type] = instance

    def resolve(self, broker_id: str, extension_type: type[T]) -> T | None:
        """Get an extension, or ``None`` if not registered."""
        broker_exts = self._extensions.get(broker_id, {})
        instance = broker_exts.get(extension_type)
        return instance if isinstance(instance, extension_type) else None

    def supports(self, broker_id: str, extension_type: type[T]) -> bool:
        """Check if a broker supports a specific extension type."""
        return self.resolve(broker_id, extension_type) is not None


# Backward-compatible alias — consumers importing ``ExtensionRegistry``
# from ``brokers.ports`` continue to work without changes.
ExtensionRegistry = DictExtensionRegistry

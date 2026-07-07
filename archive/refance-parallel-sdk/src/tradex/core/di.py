"""Dependency injection container.

Lightweight service locator for wiring SDK components together.
Providers register their implementations; consumers resolve dependencies.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, TypeVar

from tradex.core.errors import ConfigurationError
from tradex.core.logging_config import get_logger

logger = get_logger("core.di")

T = TypeVar("T")


class Container:
    """Simple dependency injection container.

    Supports:
    - Singleton registration (one instance, shared)
    - Factory registration (new instance per resolve)
    - Class registration (auto-instantiated singleton)

    Usage:
        container = Container()
        container.register_instance(EventBus(), EventBus)
        container.register_factory(lambda: RateLimiter(config), RateLimiter)

        bus = container.resolve(EventBus)
    """

    def __init__(self) -> None:
        self._singletons: dict[type, Any] = {}
        self._factories: dict[type, Callable[[], Any]] = {}
        self._parent: Optional[Container] = None

    def register_instance(self, instance: Any, interface: Optional[type] = None) -> None:
        """Register a pre-built instance as a singleton.

        Args:
            instance: The object to register.
            interface: The type to register under. Defaults to type(instance).
        """
        key = interface or type(instance)
        self._singletons[key] = instance
        logger.debug("registered_instance", type=key.__name__)

    def register_factory(self, factory: Callable[[], Any], interface: type) -> None:
        """Register a factory function.

        The factory is called once on first resolve, then cached.

        Args:
            factory: Callable that returns an instance of interface.
            interface: The type to register under.
        """
        self._factories[interface] = factory
        logger.debug("registered_factory", type=interface.__name__)

    def register_class(self, cls: type, interface: Optional[type] = None) -> None:
        """Register a class for auto-instantiation.

        The class is instantiated with no args on first resolve.

        Args:
            cls: The class to instantiate.
            interface: The type to register under. Defaults to cls.
        """
        key = interface or cls
        self._factories[key] = lambda: cls()
        logger.debug("registered_class", type=key.__name__)

    def resolve(self, interface: type) -> Any:
        """Resolve an instance by type.

        Checks singletons first, then factories, then parent container.

        Args:
            interface: The type to resolve.

        Returns:
            An instance of the requested type.

        Raises:
            ConfigurationError: If no registration found.
        """
        # Check singletons
        if interface in self._singletons:
            return self._singletons[interface]

        # Check factories (create and cache as singleton)
        if interface in self._factories:
            instance = self._factories[interface]()
            self._singletons[interface] = instance
            return instance

        # Check parent
        if self._parent:
            return self._parent.resolve(interface)

        raise ConfigurationError(
            f"No registration found for {interface.__name__}",
            code="DI_RESOLUTION_ERROR",
        )

    def has(self, interface: type) -> bool:
        """Check if a type is registered."""
        return (
            interface in self._singletons
            or interface in self._factories
            or (self._parent is not None and self._parent.has(interface))
        )

    def create_child(self) -> Container:
        """Create a child container that inherits from this one."""
        child = Container()
        child._parent = self
        return child

    def clear(self) -> None:
        """Clear all registrations."""
        self._singletons.clear()
        self._factories.clear()

    @property
    def registered_types(self) -> list[type]:
        """List all registered types."""
        types = set(self._singletons.keys()) | set(self._factories.keys())
        if self._parent:
            types |= set(self._parent.registered_types)
        return list(types)

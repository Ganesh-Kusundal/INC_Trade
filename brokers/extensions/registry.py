"""Extension Decorator Registry — auto-applies instrument decorators by capability.

Maps broker capabilities to decorator factories. When an adapter creates
an instrument via ``InstrumentFactory``, the registry is consulted and
applicable decorators are applied automatically.

Usage::

    from decimal import Decimal
    from brokers.extensions.registry import ExtensionDecoratorRegistry
    from brokers.market.instrument import Instrument

    registry = ExtensionDecoratorRegistry()

    # Register a depth decorator for a capability key
    registry.register("depth_200", lambda inst, dp=None: Depth200Decorator(inst, dp))

    # Later, when creating an instrument with known capabilities:
    caps = {"depth_200": 200, "depth_provider": adapter}
    inst = registry.apply(inst, caps)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

if TYPE_CHECKING:
    from brokers.market.instrument import Instrument

logger = logging.getLogger(__name__)

# Type for a decorator factory: (instrument, **kwargs) -> decorated instrument
DecoratorFactory = Callable[..., Any]


class ExtensionDecoratorRegistry:
    """Registry mapping capability keys to decorator factories.

    The registry allows broker adapters or the factory to declare what
    decorators to apply based on capabilities, rather than hardcoding
    depth levels in each adapter's ``instrument()`` method.
    """

    def __init__(self) -> None:
        self._factories: dict[str, DecoratorFactory] = {}

    def register(
        self,
        capability_key: str,
        factory: DecoratorFactory,
        *,
        override: bool = False,
    ) -> None:
        """Register a decorator factory for a capability key.

        Args:
            capability_key: e.g. ``"depth_200"``, ``"cache_2s"``, ``"logging"``.
            factory: Callable that takes ``(instrument, **kwargs)`` and
                returns a decorated instrument.
            override: If True, replaces any existing factory for this key.

        Raises:
            ValueError: If the key is already registered and ``override`` is False.
        """
        if capability_key in self._factories and not override:
            raise ValueError(
                f"Decorator factory already registered for {capability_key!r}. "
                "Use override=True to replace."
            )
        self._factories[capability_key] = factory
        logger.debug("registered decorator factory for %r", capability_key)

    def unregister(self, capability_key: str) -> None:
        """Remove a registered decorator factory."""
        self._factories.pop(capability_key, None)

    def get_factory(self, capability_key: str) -> DecoratorFactory | None:
        """Look up a decorator factory by capability key."""
        return self._factories.get(capability_key)

    def apply(
        self,
        instrument: Any,
        capabilities: dict[str, Any],
    ) -> Any:
        """Apply all registered decorators matching the given capabilities.

        Iterates over the capabilities dict in insertion order of the
        registry (not the dict). For each matching capability key whose
        value is truthy, the decorator factory is called and the result
        becomes the new instrument.

        Args:
            instrument: The base ``Instrument`` (or already-decorated).
            capabilities: Dict mapping capability keys to their config values.
                A non-None, non-zero value triggers the decorator. The value
                is passed as a keyword argument to the factory.

        Returns:
            The instrument with all matching decorators applied in sequence.
        """
        result = instrument
        for key, factory in self._factories.items():
            config = capabilities.get(key)
            if config is not None and config != 0 and config is not False:
                try:
                    result = factory(result, **{key: config})
                except TypeError:
                    # Factory may not accept the config kwarg; try without
                    result = factory(result)
        return result

    def apply_from_adapter(
        self,
        instrument: Any,
        adapter: Any,
    ) -> Any:
        """Apply decorators based on an adapter's capabilities.

        Checks the adapter for known capability attributes and applies
        matching decorators.

        Args:
            instrument: The base ``Instrument``.
            adapter: A ``BrokerAdapter`` instance.

        Returns:
            The instrument with matching decorators applied.
        """
        caps: dict[str, Any] = {}

        # Depth capability
        max_levels = getattr(adapter, "max_levels", 5)
        if max_levels > 5:
            depth_key = f"depth_{max_levels}"
            caps[depth_key] = max_levels

        return self.apply(instrument, caps)

    def has_key(self, capability_key: str) -> bool:
        """Check if a capability key has a registered factory."""
        return capability_key in self._factories

    @property
    def registered_keys(self) -> frozenset[str]:
        """Return all registered capability keys."""
        return frozenset(self._factories.keys())

    def __repr__(self) -> str:
        keys = ", ".join(sorted(self._factories.keys()))
        return f"ExtensionDecoratorRegistry({keys})"


_default_registry: ExtensionDecoratorRegistry | None = None


def get_default_registry() -> ExtensionDecoratorRegistry:
    """Get the singleton default registry with pre-populated factories."""
    global _default_registry
    if _default_registry is None:
        _default_registry = ExtensionDecoratorRegistry()
        _populate_default_registry(_default_registry)
    return _default_registry


def reset_default_registry() -> None:
    """Reset the default registry singleton. For testing."""
    global _default_registry
    _default_registry = None


def _populate_default_registry(registry: ExtensionDecoratorRegistry) -> None:
    """Populate the registry with default decorator factories."""
    from brokers.market.depth_decorators import Depth20Decorator, Depth30Decorator, Depth200Decorator
    from brokers.market.cache_decorator import CachedDecorator
    from brokers.market.log_decorator import LoggedDecorator

    def _make_depth_20(instrument: Instrument, **_: Any) -> Depth20Decorator:
        dp = getattr(instrument, "_depth_provider", None)
        if dp is None:
            dp = MagicMock()
        return Depth20Decorator(instrument, dp)

    def _make_depth_30(instrument: Instrument, **_: Any) -> Depth30Decorator:
        dp = getattr(instrument, "_depth_provider", None)
        if dp is None:
            dp = MagicMock()
        return Depth30Decorator(instrument, dp)

    def _make_depth_200(instrument: Instrument, **_: Any) -> Depth200Decorator:
        dp = getattr(instrument, "_depth_provider", None)
        if dp is None:
            dp = MagicMock()
        return Depth200Decorator(instrument, dp)

    registry.register("depth_20", _make_depth_20)
    registry.register("depth_30", _make_depth_30)
    registry.register("depth_200", _make_depth_200)
    registry.register("cache", CachedDecorator)
    registry.register("logging", LoggedDecorator)

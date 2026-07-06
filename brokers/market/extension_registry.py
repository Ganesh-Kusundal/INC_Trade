"""Default extension decorator registry wiring for the market layer."""

from __future__ import annotations

from typing import Any

from brokers.extensions.registry import ExtensionDecoratorRegistry

_default_registry: ExtensionDecoratorRegistry | None = None


def get_default_extension_registry() -> ExtensionDecoratorRegistry:
    """Get or create the default extension decorator registry."""
    global _default_registry

    if _default_registry is not None:
        return _default_registry

    registry = ExtensionDecoratorRegistry()

    def _depth_factory(instrument: Any, **kwargs: Any) -> Any:
        from brokers.market.decorators import with_depth

        depth_value = (
            kwargs.get("depth_200") or kwargs.get("depth_30") or kwargs.get("depth_20") or 0
        )
        depth_provider = getattr(instrument, "_depth_provider", None) or getattr(
            instrument, "_provider", None
        )
        return with_depth(instrument, levels=int(depth_value), depth_provider=depth_provider)

    registry.register("depth_20", _depth_factory)
    registry.register("depth_30", _depth_factory)
    registry.register("depth_200", _depth_factory)

    def _cache_factory(instrument: Any, **kwargs: Any) -> Any:
        from brokers.market.decorators import with_cache

        ttl = float(kwargs.get("cache_ttl", 2.0))
        return with_cache(instrument, ttl_seconds=ttl)

    registry.register("cache", _cache_factory)

    def _log_factory(instrument: Any, **kwargs: Any) -> Any:
        from brokers.market.decorators import with_logging

        return with_logging(instrument)

    registry.register("logging", _log_factory)

    _default_registry = registry
    return registry


def reset_default_extension_registry() -> None:
    """Reset the default registry (primarily for testing)."""
    global _default_registry
    _default_registry = None

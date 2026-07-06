"""Depth Decorators — broker-specific depth level extensions.

Decorator pattern wraps a base Instrument to add support for
non-standard depth levels (20, 30, 200) via a DepthProvider.

All depth decorators extend ``InstrumentDecorator``, enabling stacking::

    from brokers_core.market.depth_decorators import Depth200Decorator
    from brokers_core.market.cache_decorator import CachedDecorator

    inst = CachedDecorator(Depth200Decorator(base_instrument, provider))
    depth = inst.depth(200)  # 200-level market depth
    quote = inst.quote()     # cached quote via CachedDecorator
"""

from __future__ import annotations

from typing import Any

from brokers_core.market.decorators import InstrumentDecorator
from brokers_core.market.instrument import Instrument


class DepthDecorator(InstrumentDecorator):
    """Abstract base for depth-level decorators.

    Wraps an Instrument and delegates all attribute access to it
    (via ``InstrumentDecorator.__getattr__``), except for depth-related
    methods which use a ``DepthProvider``.

    Attributes:
        _wrapped: The wrapped Instrument instance (via InstrumentDecorator).
        _depth_provider: DepthProvider protocol implementation.
    """

    def __init__(self, instrument: Instrument, depth_provider: Any) -> None:
        super().__init__(instrument)
        object.__setattr__(self, "_depth_provider", depth_provider)

    def depth(self, levels: int = 5) -> Any:
        """Get market depth with requested levels."""
        return self._depth_provider.depth(
            self._wrapped.symbol,
            self._wrapped.exchange,
            levels,
        )

    def supports_depth(self, levels: int) -> bool:
        """Check if this decorator supports the requested depth level."""
        caps = getattr(self._wrapped, "_capabilities", None)
        if caps is not None:
            return caps.supports_depth(levels)
        return levels <= 5  # Default: only 5-level depth assumed


class Depth20Decorator(DepthDecorator):
    """Decorator adding 20-level depth support.

    Dhan-specific: wraps an instrument to enable 20-level market depth
    via WebSocket or REST. Max 50 instruments per connection.
    """

    def depth_20(self) -> Any:
        """Get 20-level market depth."""
        return self.depth(levels=20)


class Depth30Decorator(DepthDecorator):
    """Decorator adding 30-level depth support.

    Upstox-specific: wraps an instrument to enable 30-level market depth.
    """

    def depth_30(self) -> Any:
        """Get 30-level market depth."""
        return self.depth(levels=30)


class Depth200Decorator(Depth20Decorator):
    """Decorator adding 200-level depth support.

    Dhan-specific: wraps an instrument to enable 200-level market depth
    via WebSocket. CRITICAL: Only 1 instrument per connection allowed.
    Inherits ``depth_20()`` from ``Depth20Decorator``.
    """

    def depth_200(self) -> Any:
        """Get 200-level market depth."""
        return self.depth(levels=200)

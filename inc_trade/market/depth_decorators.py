"""Depth Decorators — broker-specific depth level extensions.

Decorator pattern wraps a base Instrument to add support for
non-standard depth levels (20, 30, 200) via a DepthProvider.

Usage::

    from inc_trade.market.depth_decorators import Depth200Decorator

    inst = Depth200Decorator(base_instrument, dhan_depth_provider)
    depth = inst.depth_200()  # 200-level market depth
"""

from __future__ import annotations

from typing import Any

from inc_trade.market.instrument import Instrument


class DepthDecorator:
    """Abstract base for depth-level decorators.

    Wraps an Instrument and delegates all attribute access to it,
    except for depth-related methods which use a DepthProvider.

    Attributes:
        _instrument: The wrapped Instrument instance.
        _depth_provider: DepthProvider protocol implementation.
    """

    def __init__(self, instrument: Instrument, depth_provider: Any) -> None:
        object.__setattr__(self, "_instrument", instrument)
        object.__setattr__(self, "_depth_provider", depth_provider)

    def depth(self, levels: int = 5) -> Any:
        """Get market depth with requested levels."""
        return self._depth_provider.depth(
            self._instrument.symbol,
            self._instrument.exchange,
            levels,
        )

    def supports_depth(self, levels: int) -> bool:
        """Check if this decorator supports the requested depth level."""
        caps = self._instrument.capabilities()
        if caps is not None:
            return caps.supports_depth(levels)
        return False

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attributes to the wrapped instrument."""
        return getattr(self._instrument, name)

    def __repr__(self) -> str:
        cls = type(self).__name__
        inst = self._instrument
        return f"{cls}({inst.composite_key})"


class Depth20Decorator(DepthDecorator):
    """Decorator adding 20-level depth support."""

    def depth_20(self) -> Any:
        """Get 20-level market depth."""
        return self.depth(levels=20)


class Depth30Decorator(DepthDecorator):
    """Decorator adding 30-level depth support."""

    def depth_30(self) -> Any:
        """Get 30-level market depth."""
        return self.depth(levels=30)


class Depth200Decorator(Depth20Decorator):
    """Decorator adding 200-level depth support (inherits 20-level too)."""

    def depth_200(self) -> Any:
        """Get 200-level market depth."""
        return self.depth(levels=200)

"""InstrumentDecorator — base class for instrument extension decorators.

The Decorator Pattern allows stacking behavior on Instruments without
modifying the base class or using inheritance explosion::

    inst = LoggedDecorator(CachedDecorator(Depth200Decorator(base_inst)))
    inst.quote()       # → Logged → Cached → Depth200 → base.quote()
    inst.depth(200)    # → Depth200 → base.depth(200)

Composition helpers::

    from inc_trade.market.decorators import with_depth, with_cache, with_logging

    inst = with_logging(with_cache(with_depth(base_inst, levels=200)))
"""

from __future__ import annotations

from typing import Any

from inc_trade.market.instrument import Instrument


class InstrumentDecorator:
    """Base decorator wrapping an Instrument.

    Delegates all attribute access to the wrapped instrument via
    ``__getattr__``, allowing subclasses to override only the methods
    they need to extend.

    Usage::

        class Depth200Decorator(InstrumentDecorator):
            def depth(self, levels: int = 200) -> Any:
                return self._wrapped.depth(levels)
    """

    def __init__(self, instrument: Instrument) -> None:
        object.__setattr__(self, "_wrapped", instrument)

    def __getattr__(self, name: str) -> Any:
        """Delegate all unknown attributes to the wrapped instrument."""
        return getattr(self._wrapped, name)

    def __repr__(self) -> str:
        cls = type(self).__name__
        wrapped = self._wrapped
        return f"{cls}({wrapped.composite_key})"


# ── Composition Helpers ──────────────────────────────────────────────────


def with_depth(
    instrument: Instrument,
    levels: int = 5,
    depth_provider: Any = None,
) -> Instrument | InstrumentDecorator:
    """Add market depth extension to an instrument.

    Selects the correct decorator based on requested levels.
    No wrapper is needed for ``levels <= 5`` since the base Instrument
    already supports standard depth.

    Args:
        instrument: The base Instrument (or already-decorated).
        levels: Maximum depth levels (5, 20, 30, or 200).
        depth_provider: DepthProvider implementation. If None, the
            wrapped instrument's ``_provider`` is used as fallback.

    Returns:
        The instrument with depth extension applied, or the original
        instrument if levels <= 5.
    """
    if levels <= 5:
        return instrument

    from inc_trade.market.depth_decorators import (
        Depth20Decorator,
        Depth30Decorator,
        Depth200Decorator,
    )

    if levels <= 20:
        return Depth20Decorator(instrument, depth_provider)
    if levels <= 30:
        return Depth30Decorator(instrument, depth_provider)
    if levels <= 200:
        return Depth200Decorator(instrument, depth_provider)
    raise ValueError(f"Unsupported depth levels: {levels}. Max supported: 200.")


def with_cache(
    instrument: Instrument,
    ttl_seconds: float = 2.0,
) -> InstrumentDecorator:
    """Add quote caching to an instrument.

    Args:
        instrument: The base Instrument (or already-decorated).
        ttl_seconds: Cache TTL in seconds (default 2.0).

    Returns:
        A CachedDecorator wrapping the instrument.
    """
    from inc_trade.market.cache_decorator import CachedDecorator

    return CachedDecorator(instrument, ttl_seconds=ttl_seconds)


def with_logging(instrument: Instrument) -> InstrumentDecorator:
    """Add method-call logging to an instrument.

    All public data-access and order methods will be logged.

    Args:
        instrument: The base Instrument (or already-decorated).

    Returns:
        A LoggedDecorator wrapping the instrument.
    """
    from inc_trade.market.log_decorator import LoggedDecorator

    return LoggedDecorator(instrument)

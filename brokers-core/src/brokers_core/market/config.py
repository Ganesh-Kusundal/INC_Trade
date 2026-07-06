"""Type-safe configuration for MarketDataContext.

Groups the 11 optional dependencies of :class:`MarketDataContext` into a single
immutable value object so call sites can prepare the configuration without long
argument lists. The dataclass lives in ``brokers.market`` (the layer that owns
the context), and uses ``Any`` typing on purpose: importing the concrete port
protocols here would create circular imports during package initialization.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MarketDataConfig:
    """Immutable configuration for :class:`brokers.market.context.MarketDataContext`.

    All fields are optional; the defaults mirror ``MarketDataContext.__init__``.
    Passing a ``MarketDataConfig`` instance to ``MarketDataContext.__init__`` is
    mutually exclusive with passing any of its fields directly via kwargs:
    when both are provided, the config object wins and the individual kwargs
    are ignored.
    """

    historical: Any | None = None
    historical_router: Any | None = None
    options: Any | None = None
    streaming: Any | None = None
    instrument_port: Any | None = None
    subscription_manager: Any | None = None
    streaming_router: Any | None = None
    event_bus: Any | None = None
    degraded_mode: Any | None = None
    broker_id: str = ""
    market_router: Any | None = None

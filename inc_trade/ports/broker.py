"""Core broker gateway interface (DEPRECATED).

This module is deprecated. Use ``inc_trade.adapters.broker_adapter``
(BrokerAdapter protocol) for new code. The ``BrokerGateway`` protocol
is retained for backward compatibility and will be removed in a future
release.

Migration:
    - Replace ``BrokerGateway`` with ``BrokerAdapter``
    - Replace ``gw.market_data.quote(sym, ex)`` with ``adapter.quote(sym, ex)``
    - Replace ``gw.orders.place_order(...)`` with ``adapter.place_order(...)``
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Protocol, runtime_checkable

warnings.warn(
    "BrokerGateway is deprecated. Use BrokerAdapter instead. "
    "See inc_trade.adapters.broker_adapter.BrokerAdapter",
    DeprecationWarning,
    stacklevel=2,
)

if TYPE_CHECKING:
    from inc_trade.ports.auth import AuthPort
    from inc_trade.ports.capabilities import Capabilities
    from inc_trade.ports.extension_registry import ExtensionRegistryPort
    from inc_trade.ports.historical import HistoricalPort
    from inc_trade.ports.instruments import InstrumentPort
    from inc_trade.ports.market_data import MarketDataPort
    from inc_trade.ports.options import OptionsPort
    from inc_trade.ports.order_execution import OrderExecutionPort
    from inc_trade.ports.portfolio import PortfolioPort
    from inc_trade.ports.streaming import StreamingPort


@runtime_checkable
class BrokerGateway(Protocol):
    """Primary interface for all broker adapters (DEPRECATED).

    .. deprecated::
        ``BrokerGateway`` is deprecated. Use ``BrokerAdapter``
        (``inc_trade.adapters.broker_adapter.BrokerAdapter``) instead.

    Brokers implement this interface to provide access to their services.
    Clients should depend on ``BrokerAdapter``, not ``BrokerGateway``.

    Migration:
        - ``gw.market_data.quote(sym, ex)`` → ``adapter.quote(sym, ex)``
        - ``gw.orders.place_order(...)`` → ``adapter.place_order(...)``
        - ``gw.instrument(...)`` → ``adapter.instrument(...)``
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Warn when a class subclasses the deprecated BrokerGateway."""
        super().__init_subclass__(**kwargs)
        warnings.warn(
            f"{cls.__name__} inherits from deprecated BrokerGateway. Use BrokerAdapter instead.",
            DeprecationWarning,
            stacklevel=2,
        )

    @property
    def broker_id(self) -> str:
        """Unique identifier for this broker (e.g., 'dhan', 'upstox')."""
        ...

    def capabilities(self) -> Capabilities:
        """Feature discovery interface."""
        ...

    @property
    def orders(self) -> OrderExecutionPort:
        """Order execution service."""
        ...

    @property
    def market_data(self) -> MarketDataPort:
        """Market data service."""
        ...

    @property
    def portfolio(self) -> PortfolioPort:
        """Portfolio and positions service."""
        ...

    @property
    def historical(self) -> HistoricalPort:
        """Historical data service."""
        ...

    @property
    def instruments(self) -> InstrumentPort:
        """Instrument master service."""
        ...

    @property
    def options(self) -> OptionsPort | None:
        """Options/derivatives service (None if not supported)."""
        ...

    @property
    def auth(self) -> AuthPort:
        """Authentication service."""
        ...

    @property
    def streaming(self) -> StreamingPort:
        """Streaming/real-time data service."""
        ...

    @property
    def extensions(self) -> ExtensionRegistryPort:
        """Broker-specific extensions registry."""
        ...

    def close(self) -> None:
        """Close connections and release resources."""
        ...

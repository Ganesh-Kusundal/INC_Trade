"""BrokerSession — composition root for the next-gen broker public API.

This is the recommended entry point returned by ``brokers.connect()``.
It supports two construction modes:

1. **Port-injection mode** (blueprint style, used by tests and DI containers)::

       session = BrokerSession(
           broker_id="dhan",
           orders=orders_port,
           market=market_port,
           streaming=streaming_port,
           auth=auth_port,
           portfolio=portfolio_port,
           historical=historical_port,
       )

2. **Facade-delegation mode** (used by ``brokers.connect()``)::

       facade = create_broker("paper")
       session = BrokerSession(broker_id="paper", facade=facade)

Usage::

    import brokers
    broker = brokers.connect("paper")
    broker.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)
    broker.close()
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class BrokerSession:
    """Thin composition root wrapping all broker port implementations.

    Returned by ``brokers.connect()``. Clients use named properties
    (``orders``, ``market``, ``streaming``, etc.) instead of a monolithic
    gateway facade.

    Supports two construction modes — see module docstring.
    """

    def __init__(
        self,
        broker_id: str,
        *,
        # Port-injection mode (blueprint / DI style)
        orders: Any = None,
        market: Any = None,
        streaming: Any = None,
        auth: Any = None,
        portfolio: Any = None,
        historical: Any = None,
        # Facade-delegation mode (used by brokers.connect())
        facade: Any = None,
    ) -> None:
        self._broker_id = broker_id
        self._facade = facade

        # Store directly-injected ports (override facade lookup when set)
        self._orders = orders
        self._market = market
        self._streaming = streaming
        self._auth = auth
        self._portfolio = portfolio
        self._historical = historical

    # ── Port accessors ────────────────────────────────────────────────

    @property
    def broker_id(self) -> str:
        """Canonical broker identifier string."""
        return self._broker_id

    @property
    def orders(self) -> Any:
        """Order execution port."""
        if self._orders is not None:
            return self._orders
        return self._facade

    @property
    def market(self) -> Any:
        """Market data port."""
        if self._market is not None:
            return self._market
        return self._facade

    @property
    def streaming(self) -> Any:
        """Streaming port for live tick subscriptions."""
        if self._streaming is not None:
            return self._streaming
        if self._facade is not None:
            gw = getattr(self._facade, "_gateway", None)
            if gw is not None:
                return getattr(gw, "streaming", self._facade)
        return self._facade

    @property
    def auth(self) -> Any:
        """Authentication port."""
        if self._auth is not None:
            return self._auth
        if self._facade is not None:
            gw = getattr(self._facade, "_gateway", None)
            if gw is not None:
                return getattr(gw, "auth", self._facade)
        return self._facade

    @property
    def portfolio(self) -> Any:
        """Portfolio port (positions, holdings, funds)."""
        if self._portfolio is not None:
            return self._portfolio
        return self._facade

    @property
    def historical(self) -> Any:
        """Historical data port (candles)."""
        if self._historical is not None:
            return self._historical
        return self._facade

    @property
    def extensions(self) -> Any:
        """Extension registry for broker-specific capabilities."""
        if self._facade is not None:
            return self._facade.extensions
        return None

    @property
    def capabilities(self) -> Any:
        """Capability descriptor — feature flags."""
        if self._facade is not None:
            return self._facade.capabilities
        return None

    # ── Lifecycle ─────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the broker session and release all resources."""
        streaming = self.streaming
        if streaming is not None:
            disconnect = getattr(streaming, "disconnect", None)
            if disconnect is not None:
                try:
                    result = disconnect()
                    import inspect
                    if inspect.isawaitable(result):
                        import asyncio
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                loop.create_task(result)
                            else:
                                loop.run_until_complete(result)
                        except RuntimeError:
                            pass
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Error closing streaming: %s", exc)

        # Delegate to facade close if available
        if self._facade is not None:
            close_fn = getattr(self._facade, "close", None)
            if close_fn is not None:
                try:
                    close_fn()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Error closing facade: %s", exc)

    def __repr__(self) -> str:
        return f"BrokerSession(broker_id={self._broker_id!r})"

    def __enter__(self) -> "BrokerSession":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

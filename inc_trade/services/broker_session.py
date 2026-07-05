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
        facade: Any = None,
        **ports: Any,
    ) -> None:
        self._broker_id = broker_id
        self._facade = facade

        # Store directly-injected ports (override facade lookup when set)
        self._orders = ports.get("orders")
        self._market = ports.get("market")
        self._streaming = ports.get("streaming")
        self._auth = ports.get("auth")
        self._portfolio = ports.get("portfolio")
        self._historical = ports.get("historical")
        self._replay = None
        self._audit = ports.get("audit")
        self._cached_market = None  # Lazy cache for facade-built market context

    # ── Extended port accessors ─────────────────────────────────────────

    @property
    def scanner(self) -> Any:
        """Market scanner for evaluating scan criteria.

        Returns a ``Scanner`` instance when a market context is available,
        ``None`` otherwise.
        """
        mkt = self._market
        if mkt is None and self._facade is not None:
            mkt = self.market
        if mkt is not None:
            import inc_trade.market.scanner as _ms

            return _ms.Scanner(
                registry=mkt._registry,
                market_data=mkt._market_data,
            )
        return None

    @property
    def replay(self) -> Any:
        """Replay engine for replaying historical data as live ticks.

        Lazy-initialized and cached. Works without a market context.
        """
        if self._replay is None:
            import brokers.adapters.replay as _re

            self._replay = _re.ReplayEngine()
        return self._replay

    @property
    def degraded_mode(self) -> Any:
        """Degraded mode tracker for graceful degradation.

        Returns the ``DegradedMode`` instance from the market context
        when available, ``None`` otherwise.
        """
        mkt = self._market
        if mkt is None and self._facade is not None:
            mkt = self.market
        if mkt is not None and hasattr(mkt, "_degraded_mode"):
            return mkt._degraded_mode
        return None

    @property
    def analytics(self) -> Any:
        """Analytics calculators namespace.

        Returns a namespace with calculator classes:
        - ``vwap``: VWAPCalculator
        - ``greeks``: GreeksCalculator
        - ``atr``: ATRCalculator
        - ``volume_profile``: VolumeProfile
        - ``order_flow``: OrderFlowAnalyzer class
        - ``make_order_flow_analyzer(large_trade_threshold=100)``: factory method
        """
        from types import SimpleNamespace

        import inc_trade.market.analytics as _ma

        def _make_order_flow_analyzer(
            large_trade_threshold: int = 100,
        ) -> _ma.OrderFlowAnalyzer:
            return _ma.OrderFlowAnalyzer(large_trade_threshold=large_trade_threshold)

        return SimpleNamespace(
            vwap=_ma.VWAPCalculator,
            greeks=_ma.GreeksCalculator,
            atr=_ma.ATRCalculator,
            volume_profile=_ma.VolumeProfile,
            order_flow=_ma.OrderFlowAnalyzer,
            make_order_flow_analyzer=_make_order_flow_analyzer,
        )

    @property
    def trading(self) -> Any:
        """Trading context for account management.

        Creates a ``TradingContext`` using the facade's gateway ports
        when a facade is available, ``None`` otherwise.
        """
        if self._facade is not None:
            import inc_trade.trading.account_registry as _tar
            import inc_trade.trading.context as _tc

            gateway = self._facade._gateway
            registry = _tar.AccountRegistry()
            return _tc.TradingContext(
                registry=registry,
                order_execution=gateway.orders,
                portfolio=gateway.portfolio,
                broker_id=self._broker_id,
            )
        return None

    @property
    def audit(self) -> Any:
        """Audit facade for read-only order state history.

        Returns the injected ``AuditFacade`` when provided, ``None`` otherwise.
        """
        return self._audit

    # ── Basic identity ──────────────────────────────────────────────────

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
        """Market data port.

        Returns a ``MarketDataContext`` that exposes only market-related methods
        (``quote()``, ``depth()``, etc.) without trading methods.
        """
        if self._market is not None:
            return self._market
        if self._facade is not None:
            if self._cached_market is None:
                from inc_trade.market.context import MarketDataContext
                from inc_trade.market.instrument_registry import InstrumentRegistry

                gateway = self._facade._gateway
                self._cached_market = MarketDataContext(
                    registry=InstrumentRegistry(),
                    market_data=gateway.market_data,
                    historical=gateway.historical,
                    streaming=getattr(gateway, "streaming", None),
                    options=getattr(gateway, "options", None),
                    instrument_port=getattr(gateway, "instruments", None),
                    broker_id=self._broker_id,
                )
            return self._cached_market
        return self._facade

    @property
    def streaming(self) -> Any:
        """Streaming port for live tick subscriptions."""
        if self._streaming is not None:
            return self._streaming
        if self._facade is not None:
            return getattr(self._facade, "streaming", self._facade)
        return self._facade

    @property
    def auth(self) -> Any:
        """Authentication port."""
        if self._auth is not None:
            return self._auth
        if self._facade is not None:
            return getattr(self._facade, "auth", self._facade)
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
        import time

        streaming = self.streaming
        if streaming is not None:
            disconnect = getattr(streaming, "disconnect", None)
            if disconnect is not None:
                for attempt in range(3):
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
                        break
                    except Exception as exc:  # noqa: BLE001
                        if attempt == 2:
                            logger.warning("Error closing streaming: %s", exc)
                        else:
                            time.sleep(0.1)

        # Delegate to facade close if available
        if self._facade is not None:
            close_fn = getattr(self._facade, "close", None)
            if close_fn is not None:
                for attempt in range(3):
                    try:
                        close_fn()
                        break
                    except Exception as exc:  # noqa: BLE001
                        if attempt == 2:
                            logger.warning("Error closing facade: %s", exc)
                        else:
                            time.sleep(0.1)

    def __repr__(self) -> str:
        return f"BrokerSession(broker_id={self._broker_id!r})"

    def __enter__(self) -> "BrokerSession":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

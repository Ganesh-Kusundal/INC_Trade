"""PaperAdapter — wraps PaperGateway into the BrokerAdapter protocol.

In-memory paper trading adapter for testing and simulation. No external
dependencies, all state is held in memory.

Usage::

    from inc_trade.adapters.paper import PaperAdapter

    adapter = PaperAdapter(initial_cash=Decimal("100000"))
    adapter.connect()

    inst = adapter.instrument("RELIANCE", "NSE")
    inst.quote()     # → Quote (default LTP 100.00)
    inst.buy(qty=10) # → OrderResponse (immediately filled)
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from inc_trade.adapters.broker_adapter import BrokerAdapter

if TYPE_CHECKING:
    from datetime import datetime

    from inc_trade.domain.entities import Candle, MarketDepth, Quote

logger = logging.getLogger(__name__)


class PaperAdapter(BrokerAdapter):
    """In-memory paper trading adapter implementing BrokerAdapter protocol.

    Wraps the existing PaperGateway for testing and simulation. All
    positions and orders are held in memory and lost on disconnect.

    Capabilities:
        - Depth up to 5 levels (max_levels=5; no depth decorator applied)
        - Basic quote, order, and portfolio operations
        - No depth decorator applied by default
        - Historical data raises NotSupportedError
        - Streaming is a no-op (sync stub)

    Args:
        initial_cash: Starting cash balance. Defaults to 1,000,000.
    """

    def __init__(self, initial_cash: Decimal = Decimal("1000000.00")) -> None:
        self._initial_cash = initial_cash
        self._gw: Any = None

    @property
    def broker_id(self) -> str:
        return "paper"

    @property
    def max_levels(self) -> int:
        return 5

    @property
    def is_connected(self) -> bool:
        return self._gw is not None

    def connect(self, **credentials: Any) -> None:
        """Create the PaperGateway."""
        from brokers.adapters.paper.gateway import PaperGateway

        cash = Decimal(str(credentials.get("initial_cash", self._initial_cash)))
        self._gw = PaperGateway(initial_cash=cash)
        logger.info("PaperAdapter connected (cash=%s)", cash)

    def disconnect(self) -> None:
        """Close the gateway and release resources."""
        if self._gw is not None:
            self._gw.close()
            self._gw = None
            logger.info("PaperAdapter disconnected")

    # ── InstrumentDataProvider ────────────────────────────────────────

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        self._require_gateway()
        return self._gw.market_data.quote(symbol, exchange)

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        self._require_gateway()
        return self._gw.market_data.ltp(symbol, exchange)

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        self._require_gateway()
        return self._gw.market_data.quote_batch(symbols, exchange)

    # ── DepthProvider (also satisfies InstrumentDataProvider.depth) ──

    def depth(self, symbol: str, exchange: str = "NSE", levels: int = 5) -> MarketDepth:
        """Get market depth (5 levels max for paper trading).

        Paper trading returns an empty order book.
        """
        self._require_gateway()
        return self._gw.market_data.depth(symbol, exchange)

    # ── HistoricalDataProvider ────────────────────────────────────────

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
        resolution: str,
    ) -> list[Candle]:
        """Historical candles are not supported by paper trading."""
        self._require_gateway()
        return self._gw.historical.get_historical_candles(
            symbol,
            exchange,
            start,
            end,
            resolution,
        )

    # ── StreamingDataProvider ─────────────────────────────────────────

    def subscribe(self, instrument: Any, callback: Any) -> Any:
        """Subscribe to live market data (no-op for paper trading)."""
        self._require_gateway()
        return self._gw.streaming.subscribe(instrument, callback)

    def unsubscribe(self, instrument: Any) -> None:
        """Unsubscribe from live market data (no-op for paper trading)."""
        self._require_gateway()
        self._gw.streaming.unsubscribe(instrument)

    # ── OrderProvider ─────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: str,
        quantity: int,
        order_type: Any = None,
        price: Decimal = Decimal("0"),
        trigger_price: Decimal = Decimal("0"),
        **kwargs: Any,
    ) -> Any:
        self._require_gateway()
        from inc_trade.domain.enums import Side

        side_enum = Side.BUY if side.upper() == "BUY" else Side.SELL
        return self._gw.orders.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side_enum,
            quantity=quantity,
            order_type=order_type,
            price=price,
            trigger_price=trigger_price,
            **kwargs,
        )

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        **kwargs: Any,
    ) -> Any:
        self._require_gateway()
        return self._gw.orders.modify_order(
            order_id=order_id,
            quantity=quantity,
            price=price,
        )

    def cancel_order(self, order_id: str) -> Any:
        self._require_gateway()
        return self._gw.orders.cancel_order(order_id)

    # ── Instrument Factory ────────────────────────────────────────────

    def instrument(self, symbol: str, exchange: str, **kwargs: Any) -> Any:
        """Create an Instrument with this adapter as provider.

        Paper trading does NOT apply any depth decorator by default
        since it only supports 5-level depth.
        """
        if "apply_depth" not in kwargs:
            kwargs["apply_depth"] = 0  # No depth extension for paper
        return super().instrument(symbol, exchange, **kwargs)

    # ── Paper-Specific Helpers ─────────────────────────────────────────

    def set_quote(self, symbol: str, ltp: Decimal) -> None:
        """Set a simulated quote for testing.

        Args:
            symbol: Trading symbol.
            ltp: Last traded price to set.
        """
        self._require_gateway()
        self._gw.set_quote(symbol, ltp)

    # ── Internals ─────────────────────────────────────────────────────

    def _require_gateway(self) -> None:
        if self._gw is None:
            raise RuntimeError("PaperAdapter not connected. Call adapter.connect() first.")

"""PaperAdapter — in-memory broker adapter for testing and simulation.

Composes internal paper sub-adapters directly (no gateway). All state
is held in memory and lost when the adapter is disconnected.

Usage::

    adapter = PaperAdapter()
    adapter.connect()

    # Use as provider with BrokerSession
    session = BrokerSession(adapter)
    await session.connect()

    rel = session.equity("RELIANCE")
    query = session.query(rel)
    print(query.ltp())  # → Decimal("100.00") (default)
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from inc_trade.domain import Balance, Holding, MarketDepth, Order, OrderResponse, Position, Quote
from inc_trade.domain.enums import OrderStatus, OrderType, ProductType, Side, Validity

if TYPE_CHECKING:
    from collections.abc import Callable

    from inc_trade.domain.entities import Candle

logger = logging.getLogger(__name__)

_DEFAULT_CASH = Decimal("1000000.00")
_DEFAULT_LTP = Decimal("100.00")


class _PaperOrders:
    """In-memory order store."""

    def __init__(self) -> None:
        self._store: dict[str, Order] = {}
        self._lock = threading.Lock()

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
    ) -> OrderResponse:
        order_id = f"PAPER-{uuid.uuid4().hex[:8].upper()}"
        order = Order(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=Side.BUY if side.upper() == "BUY" else Side.SELL,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            order_type=order_type or OrderType.MARKET,
            product_type=kwargs.get("product_type", ProductType.INTRADAY),
            validity=kwargs.get("validity", Validity.DAY),
            status=OrderStatus.OPEN,
        )
        with self._lock:
            self._store[order_id] = order
        return OrderResponse(order_id=order_id, success=True, status=OrderStatus.OPEN)

    def modify_order(
        self,
        order_id: str,
        quantity: int | None = None,
        price: Decimal | None = None,
        **kwargs: Any,
    ) -> OrderResponse:
        with self._lock:
            order = self._store.get(order_id)
            if order is None:
                return OrderResponse.fail(f"Order {order_id} not found")
            self._store[order_id] = Order(
                order_id=order.order_id,
                symbol=order.symbol,
                exchange=order.exchange,
                side=order.side,
                quantity=quantity if quantity is not None else order.quantity,
                price=price if price is not None else order.price,
                trigger_price=order.trigger_price,
                order_type=order.order_type,
                product_type=order.product_type,
                validity=order.validity,
                status=order.status,
            )
        return OrderResponse(order_id=order_id, success=True, status=order.status)

    def cancel_order(self, order_id: str) -> OrderResponse:
        with self._lock:
            order = self._store.get(order_id)
            if order is None:
                return OrderResponse.fail(f"Order {order_id} not found")
            self._store[order_id] = Order(
                order_id=order.order_id,
                symbol=order.symbol,
                exchange=order.exchange,
                side=order.side,
                quantity=order.quantity,
                price=order.price,
                trigger_price=order.trigger_price,
                order_type=order.order_type,
                product_type=order.product_type,
                validity=order.validity,
                status=OrderStatus.CANCELLED,
            )
        return OrderResponse(order_id=order_id, success=True, status=OrderStatus.CANCELLED)

    def get_order(self, order_id: str) -> Order | None:
        with self._lock:
            return self._store.get(order_id)


class _PaperMarketData:
    """In-memory market data store."""

    def __init__(self) -> None:
        self._quotes: dict[str, Quote] = {}
        self._lock = threading.Lock()

    def set_quote(self, symbol: str, quote: Quote) -> None:
        with self._lock:
            self._quotes[symbol] = quote

    def set_ltp(self, symbol: str, ltp: Decimal) -> None:
        with self._lock:
            self._quotes[symbol] = Quote(symbol=symbol, ltp=ltp)

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        with self._lock:
            q = self._quotes.get(symbol)
            if q:
                return Decimal(str(q.ltp)) if not isinstance(q.ltp, Decimal) else q.ltp
        return _DEFAULT_LTP

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        with self._lock:
            q = self._quotes.get(symbol)
            if q:
                return q
        return Quote(symbol=symbol, ltp=_DEFAULT_LTP, exchange=exchange)

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        return {sym: self.quote(sym, exchange) for sym in symbols}

    def depth(self, symbol: str, exchange: str = "NSE", levels: int = 5) -> MarketDepth:
        return MarketDepth(symbol=symbol, exchange=exchange)


class _PaperHistorical:
    """In-memory historical data (returns empty candles)."""

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
        resolution: str,
    ) -> list[Any]:
        return []


class _PaperStreaming:
    """In-memory streaming (no-op)."""

    def __init__(self) -> None:
        self._callbacks: dict[str, Callable[..., Any]] = {}
        self._connected = True

    def subscribe(self, instrument: Any, callback: Callable[..., Any]) -> Any:
        symbol = getattr(instrument, "symbol", str(instrument))
        self._callbacks[symbol] = callback
        return _StreamHandle(self, symbol)

    def unsubscribe(self, instrument: Any) -> None:
        symbol = getattr(instrument, "symbol", str(instrument))
        self._callbacks.pop(symbol, None)

    @property
    def is_connected(self) -> bool:
        return self._connected

    def simulate_tick(self, symbol: str, ltp: Decimal) -> None:
        """Simulate an incoming tick for testing."""
        callback = self._callbacks.get(symbol)
        if callback:
            callback(Quote(symbol=symbol, ltp=ltp))


class _StreamHandle:
    """Subscription handle returned by PaperAdapter.subscribe()."""

    def __init__(self, streaming: _PaperStreaming, symbol: str) -> None:
        self._streaming = streaming
        self._symbol = symbol

    def unsubscribe(self) -> None:
        self._streaming.unsubscribe(self._symbol)


class PaperAdapter:
    """In-memory paper trading adapter for testing and simulation.

    All state is held in memory. No external dependencies.
    Default LTP is ``100.00`` for any symbol.

    Args:
        initial_cash: Starting cash balance (default: 1,000,000).
    """

    broker_id: str = "paper"

    def __init__(self, initial_cash: Decimal = _DEFAULT_CASH) -> None:
        self._initial_cash = initial_cash
        self._orders: _PaperOrders | None = None
        self._market_data: _PaperMarketData | None = None
        self._historical: _PaperHistorical | None = None
        self._streaming: _PaperStreaming | None = None
        self._connected: bool = False

    # ── Lifecycle ─────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Initialize all in-memory sub-adapters."""
        self._orders = _PaperOrders()
        self._market_data = _PaperMarketData()
        self._historical = _PaperHistorical()
        self._streaming = _PaperStreaming()
        self._connected = True
        logger.info("PaperAdapter connected")

    def disconnect(self) -> None:
        """Clear all in-memory state."""
        self._orders = None
        self._market_data = None
        self._historical = None
        self._streaming = None
        self._connected = False
        logger.info("PaperAdapter disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def max_levels(self) -> int:
        return 5

    # ── InstrumentDataProvider ────────────────────────────────────────────

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        self._require_connected()
        return self._market_data.quote(symbol, exchange)

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        self._require_connected()
        return self._market_data.ltp(symbol, exchange)

    def depth(self, symbol: str, exchange: str = "NSE", levels: int = 5) -> MarketDepth:
        self._require_connected()
        return self._market_data.depth(symbol, exchange, levels)

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        self._require_connected()
        return self._market_data.quote_batch(symbols, exchange)

    # ── DepthProvider ─────────────────────────────────────────────────────

    # Uses default 5-level depth from market_data

    # ── HistoricalDataProvider ────────────────────────────────────────────

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
        resolution: str,
    ) -> list[Any]:
        self._require_connected()
        return self._historical.get_candles(symbol, exchange, start, end, resolution)

    # ── StreamingDataProvider ─────────────────────────────────────────────

    def subscribe(self, instrument: Any, callback: Callable[..., Any]) -> Any:
        self._require_connected()
        return self._streaming.subscribe(instrument, callback)

    def unsubscribe(self, instrument: Any) -> None:
        self._require_connected()
        self._streaming.unsubscribe(instrument)

    # ── OrderProvider ─────────────────────────────────────────────────────

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
    ) -> OrderResponse:
        self._require_connected()
        return self._orders.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side,
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
    ) -> OrderResponse:
        self._require_connected()
        return self._orders.modify_order(order_id, quantity, price, **kwargs)

    def cancel_order(self, order_id: str) -> OrderResponse:
        self._require_connected()
        return self._orders.cancel_order(order_id)

    # ── Test Helpers ──────────────────────────────────────────────────────

    def set_quote(self, symbol: str, ltp: Decimal) -> None:
        """Set a mock quote for testing."""
        self._require_connected()
        self._market_data.set_ltp(symbol, ltp)

    def simulate_tick(self, symbol: str, ltp: Decimal) -> None:
        """Simulate an incoming streaming tick for testing."""
        self._require_connected()
        self._streaming.simulate_tick(symbol, ltp)

    # ── Internals ─────────────────────────────────────────────────────────

    def _require_connected(self) -> None:
        if not self._connected or self._market_data is None:
            raise RuntimeError("PaperAdapter not connected. Call adapter.connect() first.")

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"PaperAdapter(status={status})"

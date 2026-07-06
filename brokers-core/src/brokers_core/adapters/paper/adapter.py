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

from brokers_core.domain import Balance, Holding, MarketDepth, Order, OrderResponse, Position, Quote
from brokers_core.domain.constants.exchanges import (
    DEFAULT_DERIVATIVE_EXCHANGE,
    DEFAULT_EQUITY_EXCHANGE,
)
from brokers_core.domain.entities import OptionChain, OptionLeg, OptionStrike
from brokers_core.adapters.base import ConnectedGuard
from brokers_core.domain.constants.broker_ids import PAPER_ID
from brokers_core.domain.enums import OrderStatus, OrderType, ProductType, Side, Validity
from brokers_core.domain.exceptions import NotSupportedError

if TYPE_CHECKING:
    from collections.abc import Callable

    from brokers_core.domain.entities import Candle

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
        side: Side,
        quantity: int,
        order_type: Any = None,
        price: Decimal = Decimal("0"),
        trigger_price: Decimal = Decimal("0"),
        **kwargs: Any,
    ) -> OrderResponse:
        # Validate quantity
        if quantity <= 0:
            return OrderResponse.fail("Quantity must be greater than 0.")

        order_id = f"PAPER-{uuid.uuid4().hex[:8].upper()}"
        order = Order(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            order_type=order_type or OrderType.MARKET,
            product_type=kwargs.get("product_type", ProductType.INTRADAY),
            validity=kwargs.get("validity", Validity.DAY),
            status=OrderStatus.FILLED,  # Simulate immediate fill
            filled_quantity=quantity,  # Fully filled
        )
        with self._lock:
            self._store[order_id] = order
        return OrderResponse(order_id=order_id, success=True, status=OrderStatus.FILLED)

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

    def get_orders(self) -> list[Order]:
        with self._lock:
            return list(self._store.values())

    def get_order_book(self) -> list[Order]:
        """Return all orders (alias for get_orders)."""
        return self.get_orders()

    def get_positions(self) -> list[dict]:
        """Aggregate positions from filled orders."""
        with self._lock:
            positions: dict[tuple[str, str], dict] = {}
            for order in self._store.values():
                if order.status != OrderStatus.FILLED:
                    continue
                key = (order.symbol, order.exchange)
                if key not in positions:
                    positions[key] = {
                        "symbol": order.symbol,
                        "exchange": order.exchange,
                        "buy_quantity": 0,
                        "sell_quantity": 0,
                        "buy_value": Decimal("0"),
                        "sell_value": Decimal("0"),
                    }
                pos = positions[key]
                if order.side == Side.BUY:
                    pos["buy_quantity"] += order.quantity
                    pos["buy_value"] += order.price * order.quantity
                else:
                    pos["sell_quantity"] += order.quantity
                    pos["sell_value"] += order.price * order.quantity

            result = []
            for pos in positions.values():
                net_qty = pos["buy_quantity"] - pos["sell_quantity"]
                if net_qty > 0:
                    avg_price = (
                        pos["buy_value"] / pos["buy_quantity"]
                        if pos["buy_quantity"] > 0
                        else Decimal("0")
                    )
                elif net_qty < 0:
                    avg_price = (
                        pos["sell_value"] / pos["sell_quantity"]
                        if pos["sell_quantity"] > 0
                        else Decimal("0")
                    )
                else:
                    avg_price = Decimal("0")
                result.append(
                    {
                        "symbol": pos["symbol"],
                        "exchange": pos["exchange"],
                        "quantity": net_qty,
                        "average_price": avg_price,
                    }
                )
            return result


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

    def ltp(self, symbol: str, exchange: str = DEFAULT_EQUITY_EXCHANGE) -> Decimal:
        with self._lock:
            q = self._quotes.get(symbol)
            if q:
                return Decimal(str(q.ltp)) if not isinstance(q.ltp, Decimal) else q.ltp
        return _DEFAULT_LTP

    def quote(self, symbol: str, exchange: str = DEFAULT_EQUITY_EXCHANGE) -> Quote:
        with self._lock:
            q = self._quotes.get(symbol)
            if q:
                return q
        return Quote(symbol=symbol, ltp=_DEFAULT_LTP, exchange=exchange)

    def quote_batch(self, symbols: list[str], exchange: str = DEFAULT_EQUITY_EXCHANGE) -> dict[str, Quote]:
        return {sym: self.quote(sym, exchange) for sym in symbols}

    def depth(self, symbol: str, exchange: str = DEFAULT_EQUITY_EXCHANGE, levels: int = 5) -> MarketDepth:
        return MarketDepth(symbol=symbol, exchange=exchange)


class _PaperHistorical:
    """In-memory historical data — not supported."""

    def get_candles(
        self,
        symbol: str,
        exchange: str,
        start: datetime,
        end: datetime,
        resolution: str,
    ) -> list[Any]:
        raise NotSupportedError("PaperAdapter does not support historical candles")


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


class PaperAdapter(ConnectedGuard):
    """In-memory paper trading adapter for testing and simulation.

    All state is held in memory. No external dependencies.
    Default LTP is ``100.00`` for any symbol.

    Args:
        initial_cash: Starting cash balance (default: 1,000,000).
    """

    broker_id: str = PAPER_ID

    def __init__(self, initial_cash: Decimal = _DEFAULT_CASH) -> None:
        self._initial_cash = initial_cash
        self._orders: _PaperOrders | None = None
        self._market_data: _PaperMarketData | None = None
        self._historical: _PaperHistorical | None = None
        self._streaming: _PaperStreaming | None = None

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
    def max_levels(self) -> int:
        return 5

    # ── InstrumentDataProvider ────────────────────────────────────────────

    def quote(self, symbol: str, exchange: str = DEFAULT_EQUITY_EXCHANGE) -> Quote:
        self._require_connected()
        return self._market_data.quote(symbol, exchange)

    def ltp(self, symbol: str, exchange: str = DEFAULT_EQUITY_EXCHANGE) -> Decimal:
        self._require_connected()
        return self._market_data.ltp(symbol, exchange)

    def depth(self, symbol: str, exchange: str = DEFAULT_EQUITY_EXCHANGE, levels: int = 5) -> MarketDepth:
        self._require_connected()
        return self._market_data.depth(symbol, exchange, levels)

    def quote_batch(self, symbols: list[str], exchange: str = DEFAULT_EQUITY_EXCHANGE) -> dict[str, Quote]:
        self._require_connected()
        return self._market_data.quote_batch(symbols, exchange)

    # ── DepthProvider ─────────────────────────────────────────────────────

    # Uses default 5-level depth from market_data

    # ── get_option_chain ─────────────────────────────────────────────────

    def get_option_chain(
        self,
        underlying: str,
        exchange: str = DEFAULT_DERIVATIVE_EXCHANGE,
        expiry: str | None = None,
    ) -> OptionChain:
        """Return a simple mock option chain for paper trading."""
        self._require_connected()
        exp = expiry or "2025-01-30"
        strikes = (
            OptionStrike(
                strike=Decimal("25000"),
                call=OptionLeg(
                    ltp=Decimal("125.50"),
                    oi=100000,
                    volume=5000,
                    iv=Decimal("15.5"),
                    delta=Decimal("0.55"),
                    theta=None,
                    gamma=None,
                    vega=None,
                    security_id=None,
                    symbol=f"{underlying}25JAN30CE25000",
                ),
                put=OptionLeg(
                    ltp=Decimal("100.25"),
                    oi=120000,
                    volume=4500,
                    iv=Decimal("16.2"),
                    delta=Decimal("-0.45"),
                    theta=None,
                    gamma=None,
                    vega=None,
                    security_id=None,
                    symbol=f"{underlying}25JAN30PE25000",
                ),
            ),
            OptionStrike(
                strike=Decimal("25100"),
                call=OptionLeg(
                    ltp=Decimal("100.00"),
                    oi=80000,
                    volume=4000,
                    iv=Decimal("15.0"),
                    delta=Decimal("0.50"),
                    theta=None,
                    gamma=None,
                    vega=None,
                    security_id=None,
                    symbol=f"{underlying}25JAN30CE25100",
                ),
                put=OptionLeg(
                    ltp=Decimal("125.50"),
                    oi=90000,
                    volume=3500,
                    iv=Decimal("16.5"),
                    delta=Decimal("-0.50"),
                    theta=None,
                    gamma=None,
                    vega=None,
                    security_id=None,
                    symbol=f"{underlying}25JAN30PE25100",
                ),
            ),
        )
        return OptionChain(
            underlying=underlying,
            expiry=exp,
            spot=Decimal("25050"),
            strikes=strikes,
        )

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
        side: Side,
        quantity: int,
        order_type: Any = None,
        price: Decimal = Decimal("0"),
        trigger_price: Decimal = Decimal("0"),
        **kwargs: Any,
    ) -> OrderResponse:
        self.require_connected()
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

    def instrument(self, symbol: str, exchange: str, **kwargs: Any) -> Any:
        """Create an Instrument with this adapter injected as provider."""
        from brokers_core.market.factory import InstrumentFactory

        return InstrumentFactory.create(
            symbol=symbol,
            exchange=exchange,
            provider=self,
            depth_provider=self,
            historical_provider=self,
            streaming_provider=self,
            order_provider=self,
            **kwargs,
        )

    def get_order(self, order_id: str) -> Order | None:
        """Get a single order by ID."""
        self._require_connected()
        return self._orders.get_order(order_id)

    def get_orders(self) -> list[Order]:
        """Get all orders."""
        self._require_connected()
        return self._orders.get_orders()

    def get_positions(self) -> list[dict]:
        """Get aggregated positions from filled orders."""
        self._require_connected()
        return self._orders.get_positions()

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
        self.require_connected()
        if self._market_data is None:
            raise RuntimeError("PaperAdapter not connected. Call adapter.connect() first.")

    def __repr__(self) -> str:
        status = "connected" if self._connected else "disconnected"
        return f"PaperAdapter(status={status})"

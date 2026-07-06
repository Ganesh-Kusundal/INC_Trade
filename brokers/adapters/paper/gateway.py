"""Paper trading gateway — in-memory broker for testing and simulation.

No external dependencies. All state is held in memory and lost when
the gateway is closed.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from inc_trade.domain import (
    Balance,
    Holding,
    MarketDepth,
    Order,
    OrderResponse,
    Position,
    Quote,
    Side,
    Trade,
)
from inc_trade.domain.enums import BrokerID, OrderStatus, OrderType, ProductType, Validity
from inc_trade.ports import (
    InstrumentInfo,
)
from inc_trade.ports.extension_registry import ExtensionRegistryPort
from inc_trade.ports.streaming import StreamingPort

from brokers.adapters.paper.capabilities import paper_capabilities


class _PaperOrders:
    def __init__(self, store: dict[str, Order], lock: threading.Lock):
        self._store = store
        self._lock = lock

    def place_order(
        self,
        symbol: str,
        exchange: str,
        side: Side,
        quantity: int,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal = Decimal("0"),
        product_type: ProductType = ProductType.INTRADAY,
        validity: Validity = Validity.DAY,
        trigger_price: Decimal = Decimal("0"),
    ) -> OrderResponse:
        order_id = f"PAPER-{uuid.uuid4().hex[:8].upper()}"
        order = Order(
            order_id=order_id,
            symbol=symbol,
            exchange=exchange,
            side=side,
            quantity=quantity,
            price=price,
            trigger_price=trigger_price,
            order_type=order_type,
            product_type=product_type,
            validity=validity,
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
        order_type: OrderType | None = None,
        validity: Validity | None = None,
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
                order_type=order_type if order_type is not None else order.order_type,
                product_type=order.product_type,
                validity=validity if validity is not None else order.validity,
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

    def get_orderbook(self) -> list[Order]:
        with self._lock:
            return list(self._store.values())


class _PaperMarketData:
    def __init__(self, quotes: dict[str, Quote], lock: threading.Lock):
        self._quotes = quotes
        self._lock = lock

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        with self._lock:
            q = self._quotes.get(symbol)
            if q:
                return Decimal(q.ltp) if not isinstance(q.ltp, Decimal) else q.ltp
        return Decimal("100.00")

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        with self._lock:
            q = self._quotes.get(symbol)
            if q:
                return q
        return Quote(symbol=symbol, ltp=Decimal("100.00"), exchange=exchange)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        return MarketDepth(symbol=symbol, exchange=exchange)

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        return {sym: self.ltp(sym, exchange) for sym in symbols}

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        return {sym: self.quote(sym, exchange) for sym in symbols}


class _PaperPortfolio:
    def __init__(self, cash: Decimal):
        self._cash = cash

    def positions(self) -> list[Position]:
        return []

    def holdings(self) -> list[Holding]:
        return []

    def funds(self) -> Balance:
        return Balance(available_cash=self._cash)

    def trades(self) -> list[Trade]:
        return []


class _PaperInstruments:
    _DEFAULTS = [
        InstrumentInfo("RELIANCE", "NSE", "NSE_EQ", "Reliance Industries"),
        InstrumentInfo("TCS", "NSE", "NSE_EQ", "Tata Consultancy Services"),
        InstrumentInfo("INFY", "NSE", "NSE_EQ", "Infosys"),
        InstrumentInfo("HDFCBANK", "NSE", "NSE_EQ", "HDFC Bank"),
        InstrumentInfo("NIFTY", "NSE", "NSE_FNO", "Nifty 50", lot_size=25),
        InstrumentInfo("BANKNIFTY", "NSE", "NSE_FNO", "Bank Nifty", lot_size=30),
    ]

    def search(self, query: str, limit: int = 10) -> list[InstrumentInfo]:
        query_upper = query.upper()
        return [i for i in self._DEFAULTS if query_upper in i.symbol][:limit]

    def resolve(self, symbol: str, exchange: str = "NSE") -> InstrumentInfo | None:
        for i in self._DEFAULTS:
            if i.symbol == symbol.upper():
                return i
        return None

    def load(self) -> None:
        pass


class _PaperAuth:
    def get_token(self) -> str:
        return "paper-token"

    def refresh_token(self) -> str:
        return "paper-token-refreshed"

    def is_authenticated(self) -> bool:
        return True


class _PaperHistorical:
    def get_historical_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Any]:
        from inc_trade.domain.exceptions import NotSupportedError

        raise NotSupportedError("PaperGateway does not support historical candles.")


class _PaperOptions:
    def get_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        from inc_trade.domain.exceptions import NotSupportedError

        raise NotSupportedError("PaperGateway does not support option expiries.")

    def get_option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> Any:
        from inc_trade.domain.exceptions import NotSupportedError

        raise NotSupportedError("PaperGateway does not support option chains.")


class _PaperStreaming(StreamingPort):  # type: ignore[misc]
    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        pass

    @property
    def is_connected(self) -> bool:
        return True

    async def subscribe_quotes(
        self,
        symbols: list[str],
        exchange: str,
        callback: Callable[[Quote], Any],
    ) -> None:
        pass

    async def unsubscribe_quotes(
        self,
        symbols: list[str],
        exchange: str,
    ) -> None:
        pass


class PaperGateway:
    """In-memory paper trading gateway for testing.

    Args:
        initial_cash: Starting cash balance. Defaults to 1,000,000.
    """

    def __init__(self, initial_cash: Decimal = Decimal("1000000.00")):
        self._lock = threading.Lock()
        self._orders_store: dict[str, Order] = {}
        self._quotes: dict[str, Quote] = {}

        self._orders = _PaperOrders(self._orders_store, self._lock)
        self._market_data = _PaperMarketData(self._quotes, self._lock)
        self._portfolio = _PaperPortfolio(initial_cash)
        self._instruments = _PaperInstruments()
        self._auth = _PaperAuth()
        self._historical = _PaperHistorical()
        self._options = _PaperOptions()
        self._streaming = _PaperStreaming()

    @property
    def broker_id(self) -> BrokerID:
        return BrokerID.PAPER

    def capabilities(self) -> BrokerCapabilities:
        return paper_capabilities()

    @property
    def orders(self) -> _PaperOrders:
        return self._orders

    @property
    def market_data(self) -> _PaperMarketData:
        return self._market_data

    @property
    def portfolio(self) -> _PaperPortfolio:
        return self._portfolio

    @property
    def instruments(self) -> _PaperInstruments:
        return self._instruments

    @property
    def auth(self) -> _PaperAuth:
        return self._auth

    @property
    def historical(self) -> _PaperHistorical:
        return self._historical

    @property
    def streaming(self) -> StreamingPort:
        return self._streaming

    @property
    def extensions(self) -> ExtensionRegistryPort:
        """Registry of broker-specific extensions (empty for paper trading)."""
        if not hasattr(self, "_extension_registry"):
            from inc_trade.ports.extension_registry import DictExtensionRegistry

            self._extension_registry = DictExtensionRegistry()
        return self._extension_registry

    @property
    def options(self) -> _PaperOptions:
        return self._options

    def set_quote(self, symbol: str, ltp: Decimal) -> None:
        with self._lock:
            self._quotes[symbol] = Quote(symbol=symbol, ltp=ltp)

    def close(self) -> None:
        pass

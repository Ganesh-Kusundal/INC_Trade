"""Compatibility facade — archived BrokerGateway API over modern UpstoxGateway ports."""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any, Callable

from brokers.adapters.base_streaming import StreamHandle
from brokers.adapters.upstox.gateway import UpstoxGateway
from brokers.domain import Balance, Holding, MarketDepth, Order, OrderResponse, Position, Quote, Trade
from brokers.domain.enums import OrderType, ProductType, Side, Validity


class UpstoxCompatibilityGateway:
    """Fat-facade wrapper delegating to ``UpstoxGateway`` narrow ports."""

    def __init__(self, gateway: UpstoxGateway):
        self._gw = gateway
        self._stream_lock = threading.RLock()

    @property
    def inner(self) -> UpstoxGateway:
        return self._gw

    def place_order(
        self,
        symbol: str,
        exchange: str = "NSE",
        side: str | Side = "BUY",
        quantity: int = 1,
        price: Decimal = Decimal("0"),
        order_type: str | OrderType = "MARKET",
        product_type: str | ProductType = "INTRADAY",
        validity: str | Validity = "DAY",
        trigger_price: Decimal = Decimal("0"),
        correlation_id: str = "",
    ) -> OrderResponse:
        side_enum = side if isinstance(side, Side) else Side(str(side).upper())
        ot = (
            order_type
            if isinstance(order_type, OrderType)
            else OrderType(str(order_type).upper())
        )
        pt = (
            product_type
            if isinstance(product_type, ProductType)
            else ProductType(str(product_type).upper())
        )
        val = (
            validity
            if isinstance(validity, Validity)
            else Validity(str(validity).upper())
        )
        return self._gw.orders.place_order(
            symbol=symbol,
            exchange=exchange,
            side=side_enum,
            quantity=quantity,
            order_type=ot,
            price=price,
            product_type=pt,
            validity=val,
            trigger_price=trigger_price,
            correlation_id=correlation_id,
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        return self._gw.orders.cancel_order(order_id)

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        return self._gw.orders.modify_order(order_id, **changes)

    def get_order(self, order_id: str) -> Order | None:
        return self._gw.orders.get_order(order_id)

    def get_orderbook(self) -> list[Order]:
        return self._gw.orders.get_orderbook()

    def orderbook(self) -> list[Order]:
        return self.get_orderbook()

    def trades(self) -> list[Trade]:
        return self._gw.portfolio.trades()

    def get_trade_book(self) -> list[Trade]:
        return self.trades()

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        return self._gw.market_data.ltp(symbol, exchange)

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        return self._gw.market_data.quote(symbol, exchange)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        return self._gw.market_data.depth(symbol, exchange)

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        return self._gw.ltp_batch(symbols, exchange)

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        return self._gw.quote_batch(symbols, exchange)

    def positions(self) -> list[Position]:
        return self._gw.portfolio.positions()

    def holdings(self) -> list[Holding]:
        return self._gw.portfolio.holdings()

    def funds(self) -> Balance:
        return self._gw.portfolio.funds()

    def load_instruments(self, source: str | None = None) -> None:
        self._gw.load_instruments(source=source)

    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "ltpc",
        on_tick: Callable[[Quote | dict], None] | None = None,
    ) -> Any:
        mode_map = {"LTP": "ltpc", "FULL": "full", "ltp": "ltpc", "full": "full"}
        ws_mode = mode_map.get(mode, mode)
        streaming = self._gw.streaming
        streaming.mode = ws_mode
        streaming.on_tick = on_tick
        with self._stream_lock:
            streaming.subscribe(symbol, exchange)
            if not streaming.is_connected:
                streaming.start()

        return StreamHandle(streaming, symbol, exchange)

    def unstream(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_tick: Callable[[Quote | dict], None] | None = None,
    ) -> None:
        del on_tick
        self._gw.streaming.unsubscribe(symbol, exchange)

    def stream_depth(
        self,
        symbol: str,
        exchange: str = "NSE",
        depth_type: str = "DEPTH_5",
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> Any:
        return self._gw.stream_depth(symbol, exchange, depth_type, on_depth)

    def option_chain(
        self, underlying: str, exchange: str = "NFO", expiry: str | None = None
    ) -> dict[str, Any]:
        return self._gw.option_chain(underlying, exchange, expiry)

    def close(self) -> None:
        self._gw.close()

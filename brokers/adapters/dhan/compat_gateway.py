"""Compatibility facade — archived BrokerGateway API over modern DhanGateway ports.

Preserves the modern ISP architecture: this is an optional wrapper for legacy
call sites. New code should use ``DhanGateway`` ports directly.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable

import pandas as pd

from brokers.adapters.dhan.gateway import DhanGateway
from brokers.adapters.dhan.futures import _parse_expiry
from brokers.adapters.dhan.options import OptionChain
from brokers.domain import Balance, Holding, MarketDepth, Order, OrderResponse, Position, Quote, Trade
from brokers.domain.enums import OrderType, ProductType, Side, Validity
from brokers.domain.exceptions import InstrumentNotFoundError
from brokers.infrastructure.correlation import (
    generate_correlation_id,
    get_current_correlation_id,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FutureContract:
    symbol: str
    expiry: str | None
    lot_size: int = 1
    underlying: str = ""


@dataclass(frozen=True)
class FutureChain:
    underlying: str
    exchange: str
    contracts: tuple[FutureContract, ...] = ()

    @property
    def expiries(self) -> tuple[str, ...]:
        return tuple(c.expiry for c in self.contracts if c.expiry)


class DhanCompatibilityGateway:
    """Fat-facade wrapper delegating to ``DhanGateway`` narrow ports."""

    def __init__(self, gateway: DhanGateway):
        self._gw = gateway
        self._stream_lock = threading.RLock()

    @property
    def inner(self) -> DhanGateway:
        """Access the underlying port-based gateway."""
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
        correlation_id: str | None = None,
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
        cid = correlation_id or get_current_correlation_id() or generate_correlation_id()
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
            correlation_id=cid,
        )

    def cancel_order(self, order_id: str) -> OrderResponse:
        return self._gw.orders.cancel_order(order_id)

    def kill_switch(self, enable: bool) -> bool:
        return self._gw.orders.kill_switch(enable)

    def place_slice_order(
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
        correlation_id: str | None = None,
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
        cid = correlation_id or get_current_correlation_id() or generate_correlation_id()
        return self._gw.orders.place_slice_order(
            symbol=symbol,
            exchange=exchange,
            side=side_enum,
            quantity=quantity,
            order_type=ot,
            price=price,
            product_type=pt,
            validity=val,
            trigger_price=trigger_price,
            correlation_id=cid,
        )

    def modify_order(self, order_id: str, **changes: Any) -> OrderResponse:
        return self._gw.orders.modify_order(order_id, **changes)

    def get_order(self, order_id: str) -> Order | None:
        return self._gw.orders.get_order(order_id)

    def get_orderbook(self) -> list[Order]:
        return self._gw.orders.get_orderbook()

    def orderbook(self) -> list[Order]:
        """Alias for :meth:`get_orderbook` — archived contract name."""
        return self.get_orderbook()

    def trades(self) -> list[Trade]:
        return self._gw.portfolio.trades()

    def get_trade_book(self) -> list[Trade]:
        """Alias for :meth:`trades` — archived contract name."""
        return self._gw.orders.get_trade_book()

    def get_trade_history(
        self, from_date: str, to_date: str, page: int = 0
    ) -> list[Trade]:
        return self._gw.orders.get_trade_history(from_date, to_date, page=page)

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        return self._gw.market_data.ltp(symbol, exchange)

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        return self._gw.market_data.quote(symbol, exchange)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        return self._gw.market_data.depth(symbol, exchange)

    def ltp_batch(
        self, symbols: list[str], exchange: str = "NSE"
    ) -> dict[str, Decimal]:
        return self._gw.market_data.ltp_batch(symbols, exchange)

    def quote_batch(
        self, symbols: list[str], exchange: str = "NSE"
    ) -> dict[str, Quote]:
        return self._gw.market_data.quote_batch(symbols, exchange)

    def history(
        self,
        symbol: str,
        exchange: str = "NSE",
        timeframe: str = "1D",
        lookback_days: int = 30,
        from_date: str | None = None,
        to_date: str | None = None,
    ) -> pd.DataFrame:
        to_d = date.today()
        from_d = to_d - timedelta(days=lookback_days)
        end_time = datetime.combine(
            date.fromisoformat(to_date) if to_date else to_d,
            datetime.max.time(),
        )
        start_time = datetime.combine(
            date.fromisoformat(from_date) if from_date else from_d,
            datetime.min.time(),
        )
        try:
            candles = self._gw.historical.get_historical_candles(
                symbol,
                exchange,
                start_time,
                end_time,
                timeframe.upper(),
            )
        except InstrumentNotFoundError:
            logger.warning("history: instrument not found: %s/%s", symbol, exchange)
            return _candles_to_dataframe([], symbol, exchange, timeframe)
        return _candles_to_dataframe(candles, symbol, exchange, timeframe.upper())

    def option_chain(
        self,
        underlying: str,
        exchange: str = "NFO",
        expiry: str | None = None,
    ) -> OptionChain:
        expiries = self._gw.options.get_expiries(underlying, exchange)
        if not expiries:
            raise ValueError(f"No option expiries for {underlying}/{exchange}")
        expiry_date = expiry or expiries[0]
        return self._gw.options.get_option_chain(underlying, exchange, expiry_date)

    def future_chain(self, underlying: str, exchange: str = "NFO") -> FutureChain:
        refs = self._gw.futures.get_futures_chain(underlying, exchange)
        contracts = []
        for ref in refs:
            parsed = _parse_expiry(ref.symbol)
            contracts.append(
                FutureContract(
                    symbol=ref.symbol,
                    expiry=parsed.strftime("%Y-%m-%d") if parsed else None,
                    lot_size=ref.lot_size,
                    underlying=underlying,
                )
            )
        return FutureChain(
            underlying=underlying,
            exchange=exchange,
            contracts=tuple(contracts),
        )

    def search_instruments(self, query: str) -> list:
        return self._gw.instruments.search(query)

    def describe(self) -> dict[str, Any]:
        return {
            "broker": "Dhan",
            "instruments_loaded": True,
            "market_data": "available",
            "historical": "available",
            "options": "available",
            "futures": "available",
            "streaming": "available",
        }

    def depth_20(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_depth: Callable[[MarketDepth], Any] | None = None,
    ) -> MarketDepth:
        return self._gw.depth_20_snapshot(symbol, exchange, on_depth=on_depth)

    def _complete_depth_snapshot(
        self,
        ws_depth: MarketDepth | None,
        symbol: str,
        exchange: str,
    ) -> MarketDepth:
        needs_rest = ws_depth is None or not ws_depth.bids or not ws_depth.asks
        rest: MarketDepth | None = None
        if needs_rest:
            rest = self.depth(symbol, exchange)

        if ws_depth is None:
            return rest  # type: ignore[return-value]

        bids = ws_depth.bids if ws_depth.bids else (rest.bids if rest else [])
        asks = ws_depth.asks if ws_depth.asks else (rest.asks if rest else [])
        return MarketDepth(
            symbol=symbol,
            bids=list(bids),
            asks=list(asks),
            timestamp=ws_depth.timestamp or (rest.timestamp if rest else None),
        )

    def stream(
        self,
        symbol: str,
        exchange: str = "NSE",
        mode: str = "LTP",
        on_tick: Callable[[Any], Any] | None = None,
    ) -> Any:
        with self._stream_lock:
            streaming = self._gw.streaming
            streaming.set_mode(mode)
            if on_tick is not None:
                streaming.register_tick_handler(symbol, exchange, on_tick)
            streaming.subscribe(symbol, exchange)
            if not streaming.is_connected:
                streaming.start()
            return streaming

    def unstream(
        self,
        symbol: str,
        exchange: str = "NSE",
        on_tick: Callable[[Any], Any] | None = None,
    ) -> None:
        del on_tick
        with self._stream_lock:
            self._gw.streaming.unsubscribe(symbol, exchange)

    def stream_order(self, on_order: Callable[[Any], Any] | None = None) -> Any:
        with self._stream_lock:
            stream = self._gw.order_stream
            if on_order is not None:
                stream.on_order_update = on_order
            if not stream.is_connected:
                stream.start()
            return stream

    def unstream_order(self, on_order: Callable[[Any], Any] | None = None) -> None:
        del on_order
        with self._stream_lock:
            if self._gw.order_stream.is_connected:
                self._gw.order_stream.stop()

    def positions(self) -> list[Position]:
        return self._gw.portfolio.positions()

    def holdings(self) -> list[Holding]:
        return self._gw.portfolio.holdings()

    def funds(self) -> Balance:
        return self._gw.portfolio.funds()

    def load_instruments(self, source: str | None = None, use_cache: bool = True) -> None:
        del source, use_cache  # modern resolver loads on demand
        self._gw.instruments.load()

    def get_connection_status(self) -> dict[str, bool]:
        return self._gw.get_connection_status()

    def get_connection_metadata(self) -> dict[str, Any]:
        return self._gw.get_connection_metadata()

    def get_circuit_breaker_states(self) -> dict[str, int]:
        return self._gw.get_circuit_breaker_states()

    def get_token_refresh_metrics(self) -> dict[str, int]:
        return self._gw.get_token_refresh_metrics()

    def health(self) -> dict:
        return self._gw.health()

    def close(self) -> None:
        self._gw.close()


def _candles_to_dataframe(
    candles: list,
    symbol: str,
    exchange: str,
    timeframe: str,
) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "oi",
                "symbol",
                "exchange",
                "timeframe",
            ]
        )
    rows = [
        {
            "timestamp": c.timestamp,
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "volume": int(c.volume),
            "oi": 0,
            "symbol": symbol,
            "exchange": exchange,
            "timeframe": timeframe,
        }
        for c in candles
    ]
    return pd.DataFrame(rows)

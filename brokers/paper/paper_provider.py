"""Paper provider — in-memory simulation implementing the Provider protocol.

This is the reference implementation of :class:`Provider`. It simulates
all operations in-memory with no network calls, credentials, or external
dependencies.  Used for testing, development, and paper trading.

Usage::

    from brokers import Broker
    broker = Broker.paper()
    reliance = broker.instrument("RELIANCE", Exchange.NSE)
    quote = await reliance.quote()  # Simulated
"""

from __future__ import annotations

import asyncio
import itertools
import threading
from collections.abc import Callable
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from brokers.constants import DEFAULT_TICK_SIZE
from brokers.domain.account import Account, RiskPolicyProtocol
from brokers.domain.capabilities import ProviderCapabilities
from brokers.domain.enums import (
    AssetClass,
    Exchange,
    OrderStatus,
    OrderType,
    Side,
)
from brokers.infrastructure.event_bus import EventBus
from brokers.domain.historical import DateRange, HistoricalBar, HistoricalSeries
from brokers.domain.instrument import Instrument
from brokers.domain.option_chain import FutureChain, FutureContract, OptionChain, OptionContract
from brokers.domain.requests import ModifyOrderRequest, OrderRequest
from brokers.domain.values import (
    Balance,
    DepthLevel,
    Holding,
    MarketDepth,
    OrderResponse,
    Position,
    Quote,
    Subscription,
    Trade,
)
from brokers.provider.extensions import ExtensionAccess

if TYPE_CHECKING:
    pass


# Default simulated prices
_DEFAULT_PRICES: dict[str, Decimal] = {
    "RELIANCE": Decimal("2550.00"),
    "INFY": Decimal("1500.00"),
    "TCS": Decimal("3200.00"),
    "NIFTY": Decimal("25000.00"),
    "BANKNIFTY": Decimal("55000.00"),
}

_DEFAULT_LOT_SIZES: dict[str, int] = {
    "NIFTY": 75,
    "BANKNIFTY": 30,
}


class PaperProvider:
    """In-memory paper trading provider implementing the Provider protocol.

    Simulates all operations with deterministic state. Thread-safe via
    a single lock.  No network calls, no credentials.

    This is the reference implementation that every broker provider
    must match in behavior.
    """

    __slots__ = (
        "_account",
        "_balance",
        "_connected",
        "_event_bus",
        "_extensions",
        "_holdings",
        "_instruments",
        "_lock",
        "_order_counter",
        "_orders",
        "_positions",
        "_prices",
        "_quote_queues",
        "_risk_policy",
        "_trades",
    )

    def __init__(
        self,
        *,
        initial_balance: Decimal | None = None,
        event_bus: EventBus | None = None,
        risk_policy: RiskPolicyProtocol | None = None,
        **kwargs: Any,
    ) -> None:
        self._lock = threading.RLock()
        self._risk_policy = risk_policy
        bal = initial_balance or Decimal("100000")
        self._balance = Balance(
            available_balance=bal,
            sod_limit=bal,
            withdrawable_balance=bal,
        )
        self._orders: dict[str, dict[str, Any]] = {}
        self._trades: list[Trade] = []
        self._positions: dict[str, Position] = {}
        self._holdings: dict[str, Holding] = {}
        self._prices: dict[str, Decimal] = {}
        self._instruments: dict[str, Instrument] = {}
        self._order_counter = itertools.count(1)
        self._connected = False
        self._quote_queues: list[asyncio.Queue[Quote]] = []
        self._event_bus = event_bus or EventBus()
        self._extensions = ExtensionAccess(self, extensions={})
        self._account: Account | None = None
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        """Seed default market data."""
        for symbol, price in _DEFAULT_PRICES.items():
            exchange = Exchange.NFO if symbol in ("NIFTY", "BANKNIFTY") else Exchange.NSE
            asset_class = AssetClass.INDEX if symbol in ("NIFTY", "BANKNIFTY") else AssetClass.EQUITY
            key = f"{symbol}:{exchange.value}"
            self._prices[key] = price
            self._instruments[key] = Instrument(
                symbol=symbol,
                exchange=exchange,
                asset_class=asset_class,
                provider=self,
                lot_size=_DEFAULT_LOT_SIZES.get(symbol, 1),
            )

    # ── Identity ─────────────────────────────────────────────────────

    @property
    def broker_id(self) -> str:
        return "paper"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities.paper("paper")

    @property
    def risk_policy(self) -> RiskPolicyProtocol | None:
        return self._risk_policy

    @risk_policy.setter
    def risk_policy(self, value: RiskPolicyProtocol | None) -> None:
        self._risk_policy = value

    @property
    def default_account(self) -> Account:
        if self._account is None:
            self._account = Account("paper_default", self, risk_policy=self._risk_policy, event_bus=self._event_bus)
        return self._account

    @property
    def extensions(self) -> ExtensionAccess:
        return self._extensions

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Helpers ──────────────────────────────────────────────────────

    def _price_key(self, symbol: str, exchange: Exchange | str) -> str:
        exch = exchange.value if isinstance(exchange, Exchange) else exchange
        return f"{symbol}:{exch}"

    def _get_price(self, symbol: str, exchange: Exchange | str) -> Decimal:
        key = self._price_key(symbol, exchange)
        price = self._prices.get(key)
        if price is None:
            raise ValueError(f"No price for {key}")
        return price

    def set_price(self, symbol: str, exchange: Exchange, price: Decimal) -> None:
        """Set the simulated LTP for an instrument."""
        with self._lock:
            self._prices[self._price_key(symbol, exchange)] = price
            self._push_quote(Quote(symbol=symbol, ltp=price))

    def _push_quote(self, quote: Quote) -> None:
        for q in self._quote_queues:
            try:
                q.put_nowait(quote)
            except asyncio.QueueFull:
                pass

    # ── Market data ──────────────────────────────────────────────────

    async def get_quote(self, instrument: Instrument) -> Quote:
        ltp = self._get_price(instrument.symbol, instrument.exchange)
        return Quote(
            symbol=instrument.symbol,
            ltp=ltp,
            open=ltp * Decimal("0.99"),
            high=ltp * Decimal("1.01"),
            low=ltp * Decimal("0.98"),
            close=ltp * Decimal("0.995"),
            volume=100000,
            change=Decimal("0.5"),
        )

    async def get_ltp(self, instrument: Instrument) -> Decimal:
        return self._get_price(instrument.symbol, instrument.exchange)

    async def get_depth(self, instrument: Instrument) -> MarketDepth:
        ltp = self._get_price(instrument.symbol, instrument.exchange)
        bids = [
            DepthLevel(price=ltp - Decimal(str(i + 1)) * DEFAULT_TICK_SIZE, quantity=100 * (i + 1))
            for i in range(5)
        ]
        asks = [
            DepthLevel(price=ltp + Decimal(str(i + 1)) * DEFAULT_TICK_SIZE, quantity=100 * (i + 1))
            for i in range(5)
        ]
        return MarketDepth(symbol=instrument.symbol, bids=bids, asks=asks, depth_type="DEPTH_5")

    async def get_history(
        self,
        instrument: Instrument,
        *,
        timeframe: str = "1D",
        bars: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> HistoricalSeries:
        ltp = self._get_price(instrument.symbol, instrument.exchange)
        count = bars or 5
        end = to_date or date.today()
        start = from_date or date(end.year, end.month, max(1, end.day - count))

        bar_list: list[HistoricalBar] = []
        for i in range(count):
            d = date(start.year, start.month, min(28, start.day + i))
            bar_list.append(
                HistoricalBar(
                    symbol=instrument.symbol,
                    exchange=instrument.exchange.value,
                    timeframe=timeframe,
                    event_time=datetime(d.year, d.month, d.day, tzinfo=timezone.utc),
                    open=ltp * Decimal("0.99"),
                    high=ltp * Decimal("1.01"),
                    low=ltp * Decimal("0.98"),
                    close=ltp,
                    volume=100000 - i * 1000,
                )
            )
        return HistoricalSeries(
            bars=bar_list,
            coverage=DateRange(start=start, end=end),
            symbol=instrument.symbol,
            exchange=instrument.exchange.value,
            timeframe=timeframe,
        )

    # ── Instrument search ────────────────────────────────────────────

    async def search_instruments(self, query: str) -> list[Instrument]:
        q = query.upper()
        with self._lock:
            return [
                inst for key, inst in self._instruments.items()
                if q in inst.symbol.upper()
            ][:20]

    async def get_instruments(self, exchange: str | None = None) -> list[Instrument]:
        with self._lock:
            if exchange is None:
                return list(self._instruments.values())
            return [
                inst for inst in self._instruments.values()
                if inst.exchange.value == exchange
            ]

    async def resolve_instrument(self, symbol: str, exchange: str) -> Instrument:
        key = f"{symbol}:{exchange}"
        with self._lock:
            inst = self._instruments.get(key)
            if inst is not None:
                return inst
        # Create a new instrument if not found
        exch = Exchange(exchange)
        asset = AssetClass.INDEX if symbol in ("NIFTY", "BANKNIFTY") else AssetClass.EQUITY
        inst = Instrument(
            symbol=symbol,
            exchange=exch,
            asset_class=asset,
            provider=self,
            lot_size=_DEFAULT_LOT_SIZES.get(symbol, 1),
        )
        with self._lock:
            self._instruments[key] = inst
        return inst

    # ── Derivatives ──────────────────────────────────────────────────

    async def get_option_chain(
        self,
        underlying: Instrument,
        *,
        expiry: date | None = None,
    ) -> OptionChain:
        spot = self._get_price(underlying.symbol, underlying.exchange)
        exp = expiry or date(2026, 7, 31)
        atm = int(float(spot) / 100) * 100
        contracts: list[OptionContract] = []
        from brokers.domain.enums import OptionType

        for offset in [-200, -100, 0, 100, 200]:
            strike = Decimal(str(atm + offset))
            sym_call = f"{underlying.symbol}{exp.strftime('%y%m%d')}{strike}CE"
            sym_put = f"{underlying.symbol}{exp.strftime('%y%m%d')}{strike}PE"
            contracts.append(
                OptionContract(
                    instrument=Instrument(
                        symbol=sym_call,
                        exchange=underlying.exchange,
                        asset_class=AssetClass.OPTION,
                        provider=self,
                        expiry=exp,
                        strike=strike,
                        option_type=OptionType.CALL,
                    ),
                    strike=strike,
                    option_type=OptionType.CALL,
                    expiry=exp,
                    ltp=max(Decimal("1"), spot - strike + Decimal("50")),
                    oi=5000 + offset,
                    volume=1000,
                    iv=Decimal("15"),
                )
            )
            contracts.append(
                OptionContract(
                    instrument=Instrument(
                        symbol=sym_put,
                        exchange=underlying.exchange,
                        asset_class=AssetClass.OPTION,
                        provider=self,
                        expiry=exp,
                        strike=strike,
                        option_type=OptionType.PUT,
                    ),
                    strike=strike,
                    option_type=OptionType.PUT,
                    expiry=exp,
                    ltp=max(Decimal("1"), strike - spot + Decimal("50")),
                    oi=4000 - offset,
                    volume=800,
                    iv=Decimal("14"),
                )
            )
        return OptionChain(
            underlying=underlying,
            contracts=contracts,
            spot=spot,
        )

    async def get_future_chain(self, underlying: Instrument) -> FutureChain:
        sym_jul = f"{underlying.symbol}26JULFUT"
        sym_aug = f"{underlying.symbol}26AUGFUT"
        return FutureChain(
            underlying=underlying,
            contracts=[
                FutureContract(
                    instrument=Instrument(
                        symbol=sym_jul,
                        exchange=underlying.exchange,
                        asset_class=AssetClass.FUTURE,
                        provider=self,
                        expiry=date(2026, 7, 31),
                    ),
                    expiry=date(2026, 7, 31),
                    lot_size=75,
                    ltp=self._get_price(underlying.symbol, underlying.exchange),
                    oi=10000,
                ),
                FutureContract(
                    instrument=Instrument(
                        symbol=sym_aug,
                        exchange=underlying.exchange,
                        asset_class=AssetClass.FUTURE,
                        provider=self,
                        expiry=date(2026, 8, 28),
                    ),
                    expiry=date(2026, 8, 28),
                    lot_size=75,
                    ltp=self._get_price(underlying.symbol, underlying.exchange),
                    oi=8000,
                ),
            ],
        )

    # ── Execution ────────────────────────────────────────────────────

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        with self._lock:
            order_id = f"paper_{next(self._order_counter)}"
            price = request.price

            # LIMIT / STOP_LOSS orders require a positive price; never fill at zero.
            if request.order_type in (OrderType.LIMIT, OrderType.STOP_LOSS) and (
                price is None or price <= 0
            ):
                return OrderResponse.fail(
                    "LIMIT/STOP_LOSS order requires a positive price",
                    error_code="INVALID_PRICE",
                )

            # MARKET orders need a known LTP; unknown symbols must fail
            # gracefully (contract returns fail, not raise).
            if request.order_type == OrderType.MARKET or price is None or price <= 0:
                try:
                    price = self._get_price(request.symbol, request.exchange)
                except ValueError:
                    return OrderResponse.fail(
                        f"No price seeded for {request.symbol}:{request.exchange}",
                        error_code="NO_PRICE",
                    )

            # Store order
            self._orders[order_id] = {
                "order_id": order_id,
                "symbol": request.symbol,
                "exchange": request.exchange,
                "side": request.side,
                "quantity": request.quantity,
                "order_type": request.order_type,
                "product_type": request.product_type,
                "price": price,
                "status": OrderStatus.FILLED,
                "filled_quantity": request.quantity,
                "average_price": price,
            }

            # Create trade
            trade = Trade(
                trade_id=f"trade_{order_id}",
                order_id=order_id,
                symbol=request.symbol,
                exchange=request.exchange,
                side=request.side,
                quantity=request.quantity,
                price=price,
                timestamp=datetime.now(timezone.utc),
                product_type=request.product_type,
            )
            self._trades.append(trade)

            # Update position
            self._update_position(request, price)

        return OrderResponse.ok(
            order_id=order_id,
            message="Order filled (paper)",
            status=OrderStatus.FILLED,
        )

    def _update_position(self, request: OrderRequest, fill_price: Decimal) -> None:
        key = self._price_key(request.symbol, request.exchange)
        existing = self._positions.get(key)
        signed_qty = request.quantity if request.side == Side.BUY else -request.quantity

        if existing is None:
            self._positions[key] = Position(
                symbol=request.symbol,
                exchange=request.exchange,
                quantity=signed_qty,
                average_price=fill_price,
                ltp=fill_price,
                product_type=request.product_type,
            )
        else:
            new_qty = existing.quantity + signed_qty
            if new_qty == 0:
                realized = existing.realized_pnl + (
                    Decimal(str(abs(signed_qty))) * (fill_price - existing.average_price)
                    if existing.quantity > 0
                    else Decimal(str(abs(signed_qty))) * (existing.average_price - fill_price)
                )
                self._positions[key] = Position(
                    symbol=request.symbol,
                    exchange=request.exchange,
                    quantity=0,
                    average_price=Decimal("0"),
                    ltp=fill_price,
                    realized_pnl=realized,
                    product_type=request.product_type,
                )
            elif (existing.quantity > 0) == (signed_qty > 0):
                # Adding to position
                total_cost = Decimal(str(abs(existing.quantity))) * existing.average_price + Decimal(str(abs(signed_qty))) * fill_price
                new_avg = total_cost / Decimal(str(abs(new_qty)))
                self._positions[key] = Position(
                    symbol=request.symbol,
                    exchange=request.exchange,
                    quantity=new_qty,
                    average_price=new_avg,
                    ltp=fill_price,
                    realized_pnl=existing.realized_pnl,
                    product_type=request.product_type,
                )
            else:
                # Reducing position
                closed = min(abs(existing.quantity), abs(signed_qty))
                pnl_factor = Decimal("1") if existing.quantity > 0 else Decimal("-1")
                realized = existing.realized_pnl + Decimal(str(closed)) * (fill_price - existing.average_price) * pnl_factor
                self._positions[key] = Position(
                    symbol=request.symbol,
                    exchange=request.exchange,
                    quantity=new_qty,
                    average_price=existing.average_price if abs(new_qty) > 0 else Decimal("0"),
                    ltp=fill_price,
                    realized_pnl=realized,
                    product_type=request.product_type,
                )

    async def cancel_order(self, order_id: str) -> OrderResponse:
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                return OrderResponse.fail(f"Order {order_id} not found")
            if order["status"] in (OrderStatus.FILLED, OrderStatus.CANCELLED):
                return OrderResponse.fail(f"Order {order_id} already {order['status'].value}", error_code="ALREADY_EXECUTED")
            order["status"] = OrderStatus.CANCELLED
        return OrderResponse.ok(order_id=order_id, message="Order cancelled", status=OrderStatus.CANCELLED)

    async def modify_order(self, request: ModifyOrderRequest) -> OrderResponse:
        with self._lock:
            order = self._orders.get(request.order_id)
            if order is None:
                return OrderResponse.fail(f"Order {request.order_id} not found")
            if order["status"] == OrderStatus.FILLED:
                return OrderResponse.fail("Cannot modify filled order")
            if request.quantity is not None:
                order["quantity"] = request.quantity
            if request.price is not None:
                order["price"] = request.price
        return OrderResponse.ok(order_id=request.order_id, message="Order modified")

    # ── Portfolio ────────────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        with self._lock:
            return list(self._positions.values())

    async def get_balance(self) -> Balance:
        with self._lock:
            used = sum(
                (abs(Decimal(str(p.quantity))) * p.average_price for p in self._positions.values() if p.quantity != 0),
                start=Decimal("0"),
            )
            return Balance(
                available_balance=self._balance.available_balance - used,
                used_margin=used,
                total_value=self._balance.available_balance,
                sod_limit=self._balance.sod_limit,
                withdrawable_balance=self._balance.available_balance - used,
            )

    async def get_orders(self) -> list[Order]:
        from brokers.domain.order import Order
        from brokers.domain.requests import OrderRequest as OReq

        with self._lock:
            orders: list[Order] = []
            for o in self._orders.values():
                # Reconstruct OrderRequest and OrderResponse from stored dict
                req = OReq(
                    symbol=o["symbol"],
                    exchange=o["exchange"],
                    side=o["side"],
                    quantity=o["quantity"],
                    order_type=o["order_type"],
                    product_type=o["product_type"],
                    price=o["price"],
                )
                resp = OrderResponse(
                    success=True,
                    order_id=o["order_id"],
                    status=o["status"],
                )
                orders.append(Order(req, resp))
            return orders

    async def get_trades(self) -> list[Trade]:
        with self._lock:
            return list(self._trades)

    async def get_holdings(self) -> list[Holding]:
        with self._lock:
            return list(self._holdings.values())

    # ── Streaming ────────────────────────────────────────────────────

    async def subscribe_quotes(
        self,
        instruments: list[Instrument],
        *,
        on_tick: Callable[[Quote], None] | None = None,
    ) -> Subscription:
        async def _cancel() -> None:
            pass  # Paper: no real subscription to cancel

        sub = Subscription(Subscription.create_id(), _cancel)
        # If callback provided, push initial quotes
        if on_tick is not None:
            for inst in instruments:
                try:
                    q = await self.get_quote(inst)
                    on_tick(q)
                except Exception:
                    pass
        return sub

    async def subscribe_depth(
        self,
        instruments: list[Instrument],
        *,
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> Subscription:
        async def _cancel() -> None:
            pass

        sub = Subscription(Subscription.create_id(), _cancel)
        if on_depth is not None:
            for inst in instruments:
                try:
                    d = await self.get_depth(inst)
                    on_depth(d)
                except Exception:
                    pass
        return sub

    async def subscribe_orders(
        self,
        *,
        on_update: Callable[[Any], None] | None = None,
    ) -> Subscription:
        async def _cancel() -> None:
            pass

        return Subscription(Subscription.create_id(), _cancel)

    async def unsubscribe(self, subscription: Subscription) -> None:
        await subscription.cancel()

    # ── Lifecycle ────────────────────────────────────────────────────

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False


__all__ = ["PaperProvider"]

"""Dhan provider — implements the unified Provider protocol for Dhan.

Adapts the existing DhanHttpClient and DhanMapper to the new
:class:`Provider` protocol.  Methods take :class:`Instrument` objects
instead of raw symbol/exchange strings.

Usage::

    from brokers import Broker
    broker = Broker.dhan(client_id="123", access_token="tok")
    reliance = broker.instrument("RELIANCE", Exchange.NSE)
    quote = await reliance.quote()
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import date, datetime, timezone as tz
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from brokers.domain.account import Account
from brokers.domain.capabilities import ProviderCapabilities
from brokers.domain.enums import Exchange, OptionType, OrderStatus
from brokers.domain.exceptions import ProviderError
from brokers.domain.historical import DateRange, HistoricalBar, HistoricalSeries
from brokers.domain.instrument import Instrument
from brokers.domain.option_chain import FutureChain, OptionChain, OptionContract
from brokers.domain.requests import ModifyOrderRequest, OrderRequest
from brokers.domain.values import (
    Balance,
    Holding,
    MarketDepth,
    OrderResponse,
    Position,
    Quote,
    Subscription,
    Trade,
)
from brokers.common.instrument_resolver import InstrumentNotFoundError
from brokers.dhan.client import DhanHttpClient
from brokers.dhan.mapper import DhanMapper
from brokers.infrastructure.http_client import HttpError
from brokers.infrastructure.streaming.stream_health import (
    FreshnessState,
    MarketTickEvent,
    StreamHealth,
    SubscriptionState,
    TransportState,
)
from brokers.infrastructure.streaming.subscription import InstrumentKey, StreamMode
from brokers.provider.extensions import ExtensionAccess

if TYPE_CHECKING:
    from brokers.common.instrument_resolver import InstrumentResolver
    from brokers.dhan.streaming.depth_feed import DhanDepth20Feed
    from brokers.dhan.streaming.market_feed import DhanMarketFeed
    from brokers.dhan.streaming.order_feed import DhanOrderFeed

# ── Segment mapping ────────────────────────────────────────────────────────

_EXCHANGE_TO_SEGMENT: dict[str, str] = {
    "NSE": "NSE_EQ",
    "BSE": "BSE_EQ",
    "NFO": "NSE_FNO",
    "MCX": "MCX_COMM",
    "INDEX": "IDX_I",
}


def _segment_for(exchange: Exchange) -> str:
    return _EXCHANGE_TO_SEGMENT.get(exchange.value, "NSE_EQ")


_EXCHANGE_TO_INSTRUMENT: dict[str, str] = {
    "NSE": "EQUITY",
    "BSE": "EQUITY",
    "NFO": "OPTIDX",
    "MCX": "FUTCOM",
    "INDEX": "EQUITY",
}


def _instrument_type_for(exchange: Exchange) -> str:
    return _EXCHANGE_TO_INSTRUMENT.get(exchange.value, "EQUITY")


_INTERVAL_MAP: dict[str, str] = {
    "1m": "1", "1M": "1", "1": "1",
    "5m": "5", "5M": "5", "5": "5",
    "15m": "15", "15M": "15", "15": "15",
    "30m": "30", "30M": "30", "30": "30",
    "60m": "60", "60M": "60", "60": "60", "1h": "60",
}


def _interval_for(timeframe: str) -> str:
    return _INTERVAL_MAP.get(timeframe, timeframe)


class DhanProvider:
    """Dhan broker provider implementing the Provider protocol.

    Each method: resolve instrument → call HTTP client → map response →
    return domain entity.  Errors are caught and converted to
    OrderResponse.fail() for trading ops or raised as ProviderError.
    """

    __slots__ = (
        "_account",
        "_client",
        "_connected",
        "_extensions",
        "_feed_lock",
        "_instruments",
        "_market_feed",
        "_order_feed",
        "_depth_feed",
        "_resolver",
    )

    def __init__(
        self,
        *,
        client_id: str,
        access_token: str,
        instruments: dict[str, str] | None = None,
        resolver: InstrumentResolver | None = None,
        **kwargs: Any,
    ) -> None:
        self._client = DhanHttpClient(
            client_id=client_id,
            access_token=access_token,
            **kwargs,
        )
        self._instruments: dict[str, str] = instruments or {}
        self._resolver = resolver
        self._connected = False
        self._account: Account | None = None
        self._feed_lock = asyncio.Lock()

        # Streaming feeds (created lazily on first subscribe, stopped in disconnect())
        self._market_feed: DhanMarketFeed | None = None
        self._order_feed: DhanOrderFeed | None = None
        self._depth_feed: DhanDepth20Feed | None = None

        # Extended capabilities
        self._extensions = self._build_extensions()

    # ── Identity ─────────────────────────────────────────────────────

    @property
    def broker_id(self) -> str:
        return "dhan"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities.full("dhan", max_depth_levels=20)

    @property
    def default_account(self) -> Account:
        if self._account is None:
            self._account = Account("dhan_default", self)
        return self._account

    @property
    def extensions(self) -> ExtensionAccess:
        return self._extensions

    def update_token(self, new_token: str) -> None:
        """Hot-swap the access token in the underlying HTTP client.

        Called by the :class:`AuthManager` token receiver when the
        background :class:`DhanTokenScheduler` refreshes the token.
        """
        self._client.update_access_token(new_token)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def stream_health(self) -> StreamHealth:
        """Aggregate health of all streaming feeds."""
        feeds = [
            f for f in (self._market_feed, self._order_feed, self._depth_feed)
            if f is not None
        ]
        if not feeds:
            return StreamHealth(
                transport=TransportState.CLOSED,
                subscription=SubscriptionState.NONE,
                freshness=FreshnessState.UNKNOWN,
                detail="No feeds created",
            )

        running = [f.is_running for f in feeds]
        if all(running):
            transport = TransportState.OPEN
        elif any(running):
            transport = TransportState.RECONNECTING
        else:
            transport = TransportState.CLOSED

        # Aggregate subscription state across all feeds:
        # all synced → SYNCED, any partial → PARTIAL, else NONE
        any_synced = False
        any_partial = False
        total_requested = 0
        total_subscribed = 0
        for f in feeds:
            orch = getattr(f, "_orchestrator", None)
            if orch is not None:
                req = getattr(orch, "requested_count", 0)
                sub = getattr(orch, "subscribed_count", 0)
                total_requested += req
                total_subscribed += sub
                if sub > 0 and sub == req and req > 0:
                    any_synced = True
                elif sub > 0 and sub < req:
                    any_partial = True

        if any_partial:
            sub_state = SubscriptionState.PARTIAL
        elif any_synced:
            sub_state = SubscriptionState.SYNCED
        else:
            sub_state = SubscriptionState.NONE

        return StreamHealth(
            transport=transport,
            subscription=sub_state,
            freshness=FreshnessState.UNKNOWN,
            subscribed_count=total_subscribed,
            requested_count=total_requested,
        )

    # ── Helpers ──────────────────────────────────────────────────────

    def _resolve_security_id(self, instrument: Instrument) -> str:
        """Resolve instrument to Dhan security_id."""
        if instrument.security_id:
            return instrument.security_id
        key = f"{instrument.symbol}:{instrument.exchange.value}"
        sid = self._instruments.get(key)
        if sid:
            return sid
        if self._resolver is not None:
            try:
                resolved = self._resolver.resolve(instrument.symbol, instrument.exchange)
                return resolved.broker_id
            except InstrumentNotFoundError:
                pass
        return instrument.symbol

    @staticmethod
    def _require_numeric_sid(security_id: str, symbol: str) -> int:
        if not security_id.isdigit():
            raise ValueError(
                f"security_id for {symbol} is not numeric: {security_id!r}. "
                f"Populate instruments dict with correct Dhan security IDs."
            )
        return int(security_id)

    # ── Market data ──────────────────────────────────────────────────

    async def get_quote(self, instrument: Instrument) -> Quote:
        security_id = self._resolve_security_id(instrument)
        segment = _segment_for(instrument.exchange)
        sid_int = self._require_numeric_sid(security_id, instrument.symbol)
        data = self._client.get_quote(segment, [sid_int])
        segment_data = data.get("data", {}).get(segment, {})
        raw = segment_data.get(str(sid_int)) or segment_data.get(security_id)
        if raw is None:
            raise ProviderError(f"No quote data for {instrument.symbol}")
        return DhanMapper.map_quote(raw, instrument.symbol)

    async def get_ltp(self, instrument: Instrument) -> Decimal:
        security_id = self._resolve_security_id(instrument)
        segment = _segment_for(instrument.exchange)
        sid_int = self._require_numeric_sid(security_id, instrument.symbol)
        data = self._client.get_ltp(segment, [sid_int])
        segment_data = data.get("data", {}).get(segment, {})
        entry = segment_data.get(str(sid_int)) or segment_data.get(security_id)
        if entry is None:
            raise ProviderError(f"No LTP data for {instrument.symbol}")
        return Decimal(str(entry.get("last_price", 0)))

    async def get_depth(self, instrument: Instrument) -> MarketDepth:
        security_id = self._resolve_security_id(instrument)
        segment = _segment_for(instrument.exchange)
        sid_int = self._require_numeric_sid(security_id, instrument.symbol)
        data = self._client.get_quote(segment, [sid_int])
        segment_data = data.get("data", {}).get(segment, {})
        raw = segment_data.get(str(sid_int)) or segment_data.get(security_id)
        if raw is None:
            raise ProviderError(f"No depth data for {instrument.symbol}")
        return DhanMapper.map_depth(raw, instrument.symbol)

    async def get_history(
        self,
        instrument: Instrument,
        *,
        timeframe: str = "1D",
        bars: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> HistoricalSeries:
        security_id = self._resolve_security_id(instrument)
        segment = _segment_for(instrument.exchange)
        from_str = str(from_date) if from_date else "2026-01-01"
        to_str = str(to_date) if to_date else "2026-06-30"
        is_daily = timeframe.upper() in ("1D", "DAILY", "1DAY")
        endpoint = "/charts/historical" if is_daily else "/charts/intraday"
        instrument_type = _instrument_type_for(instrument.exchange)
        payload: dict[str, Any] = {
            "securityId": security_id,
            "exchangeSegment": segment,
            "instrument": instrument_type,
            "expiryCode": 0,
            "oi": True,
            "fromDate": from_str,
            "toDate": to_str,
        }
        if not is_daily:
            payload["interval"] = _interval_for(timeframe)
            payload["fromDate"] = f"{from_str} 09:15:00"
            payload["toDate"] = f"{to_str} 15:30:00"
        data = self._client.post(endpoint, json=payload)
        items = data.get("data", {}).get("ohlc", data.get("data", []))
        if isinstance(items, dict):
            items = items.get("candles", [])
        items = items if isinstance(items, list) else []

        # Convert to HistoricalBar list
        bar_list: list[HistoricalBar] = []

        for item in items:
            if isinstance(item, list) and len(item) >= 5:
                # [timestamp, open, high, low, close, volume]
                ts = datetime.fromisoformat(str(item[0]).replace("Z", "+00:00")) if item[0] else datetime.now(tz.utc)
                bar_list.append(HistoricalBar(
                    symbol=instrument.symbol,
                    exchange=instrument.exchange.value,
                    timeframe=timeframe,
                    event_time=ts,
                    open=Decimal(str(item[1])),
                    high=Decimal(str(item[2])),
                    low=Decimal(str(item[3])),
                    close=Decimal(str(item[4])),
                    volume=int(item[5]) if len(item) > 5 else 0,
                ))
            elif isinstance(item, dict):
                ts_str = item.get("date", item.get("timestamp", ""))
                ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00")) if ts_str else datetime.now(tz.utc)
                bar_list.append(HistoricalBar(
                    symbol=instrument.symbol,
                    exchange=instrument.exchange.value,
                    timeframe=timeframe,
                    event_time=ts,
                    open=Decimal(str(item.get("open", 0))),
                    high=Decimal(str(item.get("high", 0))),
                    low=Decimal(str(item.get("low", 0))),
                    close=Decimal(str(item.get("close", 0))),
                    volume=int(item.get("volume", 0)),
                ))

        start = from_date or date(2026, 1, 1)
        end = to_date or date.today()
        return HistoricalSeries(
            bars=bar_list,
            coverage=DateRange(start=start, end=end),
            symbol=instrument.symbol,
            exchange=instrument.exchange.value,
            timeframe=timeframe,
        )

    # ── Instrument search ────────────────────────────────────────────

    async def search_instruments(self, query: str) -> list[Instrument]:
        if self._resolver is not None:
            results = self._resolver.search(query, limit=20)
            return [
                Instrument(
                    symbol=r.symbol,
                    exchange=r.exchange,
                    provider=self,
                    security_id=r.broker_id,
                    lot_size=r.lot_size,
                    tick_size=r.tick_size,
                    trading_symbol=r.trading_symbol,
                )
                for r in results
            ]
        q = query.upper()
        search_results: list[Instrument] = []
        for key, sid in self._instruments.items():
            symbol = key.split(":")[0]
            if q in symbol.upper():
                exchange_str = key.split(":")[1] if ":" in key else "NSE"
                search_results.append(Instrument(
                    symbol=symbol,
                    exchange=Exchange(exchange_str),
                    provider=self,
                    security_id=sid,
                ))
                if len(search_results) >= 20:
                    break
        return search_results

    async def get_instruments(self, exchange: str | None = None) -> list[Instrument]:
        results: list[Instrument] = []
        for key, sid in self._instruments.items():
            parts = key.split(":")
            symbol = parts[0]
            exchange_str = parts[1] if len(parts) > 1 else "NSE"
            if exchange is None or exchange_str == exchange:
                results.append(Instrument(
                    symbol=symbol,
                    exchange=Exchange(exchange_str),
                    provider=self,
                    security_id=sid,
                ))
        return results

    async def resolve_instrument(self, symbol: str, exchange: str) -> Instrument:
        key = f"{symbol}:{exchange}"
        sid = self._instruments.get(key, symbol)
        lot_size = 1
        tick_size = Decimal("0.05")
        trading_symbol = ""
        if self._resolver is not None:
            try:
                resolved = self._resolver.resolve(symbol, Exchange(exchange))
                sid = resolved.broker_id
                lot_size = resolved.lot_size
                tick_size = resolved.tick_size
                trading_symbol = resolved.trading_symbol
            except InstrumentNotFoundError:
                pass
        return Instrument(
            symbol=symbol,
            exchange=Exchange(exchange),
            provider=self,
            security_id=sid,
            lot_size=lot_size,
            tick_size=tick_size,
            trading_symbol=trading_symbol,
        )

    # ── Derivatives ──────────────────────────────────────────────────

    async def get_option_chain(
        self,
        underlying: Instrument,
        *,
        expiry: date | None = None,
    ) -> OptionChain:
        segment = _segment_for(underlying.exchange)
        security_id = self._resolve_security_id(underlying)
        payload = {
            "UnderlyingScrip": self._require_numeric_sid(security_id, underlying.symbol),
            "UnderlyingSeg": segment,
            "Expiry": str(expiry) if expiry else "",
        }
        data = self._client.get_option_chain(payload)
        # Parse raw chain data into OptionContract list
        raw_chain: dict[str, Any] | list[Any] = data.get("data") or {}
        contracts: list[OptionContract] = []

        if isinstance(raw_chain, dict):
            for strike_data in raw_chain.get("strikes", raw_chain.get("data", [])):  # type: ignore[union-attr]
                if isinstance(strike_data, dict):
                    strike_val = Decimal(str(strike_data.get("strike", strike_data.get("strikePrice", 0))))
                    exp_date = expiry or date.today()

                    # Call leg
                    call_data = strike_data.get("call", strike_data.get("CE", {}))
                    if call_data:
                        contracts.append(OptionContract(
                            strike=strike_val,
                            option_type=OptionType.CALL,
                            expiry=exp_date,
                            symbol=str(call_data.get("symbol", call_data.get("tradingSymbol", ""))),
                            ltp=Decimal(str(call_data.get("ltp", 0))) if call_data.get("ltp") else None,
                            oi=int(call_data.get("oi", 0)) if call_data.get("oi") else None,
                            volume=int(call_data.get("volume", 0)) if call_data.get("volume") else None,
                        ))

                    # Put leg
                    put_data = strike_data.get("put", strike_data.get("PE", {}))
                    if put_data:
                        contracts.append(OptionContract(
                            strike=strike_val,
                            option_type=OptionType.PUT,
                            expiry=exp_date,
                            symbol=str(put_data.get("symbol", put_data.get("tradingSymbol", ""))),
                            ltp=Decimal(str(put_data.get("ltp", 0))) if put_data.get("ltp") else None,
                            oi=int(put_data.get("oi", 0)) if put_data.get("oi") else None,
                            volume=int(put_data.get("volume", 0)) if put_data.get("volume") else None,
                        ))

        spot_raw = raw_chain.get("spot", raw_chain.get("underlyingValue")) if isinstance(raw_chain, dict) else None
        spot = Decimal(str(spot_raw)) if spot_raw else None

        return OptionChain(
            underlying=underlying,
            contracts=contracts,
            spot=spot,
            provider=self,
        )

    async def get_future_chain(self, underlying: Instrument) -> FutureChain:
        # Dhan future chain endpoint varies — return empty for now
        return FutureChain(underlying=underlying, contracts=[])

    # ── Execution ────────────────────────────────────────────────────

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        try:
            # Resolve security_id via instrument lookup
            key = f"{request.symbol}:{request.exchange.value}"
            security_id = self._instruments.get(key, request.symbol)
            segment = _segment_for(request.exchange)
            payload = DhanMapper.build_order_payload(
                request, security_id, segment, self._client.client_id
            )
            data = self._client.place_order(payload)
            order_data = data.get("data", data) if isinstance(data, dict) else {}
            order_id = str(order_data.get("orderId", ""))
            return OrderResponse.ok(order_id=order_id, message="Order placed", status=OrderStatus.OPEN)
        except HttpError as exc:
            return OrderResponse.fail(str(exc), error_code="DHAN_HTTP_ERROR")
        except Exception as exc:
            return OrderResponse.fail(str(exc), error_code="INTERNAL_ERROR")

    async def cancel_order(self, order_id: str) -> OrderResponse:
        try:
            data = self._client.cancel_order(order_id)
            broker_status = str(data.get("status", "")).lower()
            if broker_status in ("success", "ok"):
                return OrderResponse.ok(order_id=order_id, message="Order cancelled", status=OrderStatus.CANCELLED)
            return OrderResponse.fail(
                str(data.get("errorMessage", "Cancel failed")),
                error_code=str(data.get("errorCode", "")),
            )
        except HttpError as exc:
            return OrderResponse.fail(str(exc), error_code="DHAN_HTTP_ERROR")

    async def modify_order(self, request: ModifyOrderRequest) -> OrderResponse:
        try:
            payload = {k: v for k, v in {"quantity": request.quantity, "price": request.price,
                                          "triggerPrice": request.trigger_price,
                                          "orderType": request.order_type.value if request.order_type else None,
                                          "validity": request.validity.value if request.validity else None,
                                          "productType": request.product_type.value if request.product_type else None}.items() if v is not None}
            data = self._client.modify_order(request.order_id, payload)
            if isinstance(data, dict) and data.get("errorCode"):
                return OrderResponse.fail(
                    str(data.get("errorMessage", "Modify failed")),
                    error_code=str(data.get("errorCode", "")),
                )
            return OrderResponse.ok(order_id=request.order_id, message="Order modified")
        except HttpError as exc:
            return OrderResponse.fail(str(exc), error_code="DHAN_HTTP_ERROR")

    # ── Portfolio ────────────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        data = self._client.get_positions()
        items = data.get("data", []) if isinstance(data, dict) else []
        return [DhanMapper.map_position(item) for item in (items if isinstance(items, list) else [])]

    async def get_balance(self) -> Balance:
        data = self._client.get_funds()
        raw = data.get("data", data) if isinstance(data, dict) else {}
        return DhanMapper.map_balance(raw if isinstance(raw, dict) else {})

    async def get_orders(self) -> list[Any]:
        data = self._client.get_orderbook()
        items = data.get("data", []) if isinstance(data, dict) else []
        return [DhanMapper.map_order(item) for item in (items if isinstance(items, list) else [])]

    async def get_trades(self) -> list[Trade]:
        data = self._client.get_trades()
        items = data.get("data", []) if isinstance(data, dict) else []
        return [DhanMapper.map_trade(item) for item in (items if isinstance(items, list) else [])]

    async def get_holdings(self) -> list[Holding]:
        data = self._client.get_holdings()
        items = data.get("data", []) if isinstance(data, dict) else []
        return [DhanMapper.map_holding(item) for item in (items if isinstance(items, list) else [])]

    # ── Streaming ────────────────────────────────────────────────────

    async def subscribe_quotes(
        self,
        instruments: list[Instrument],
        *,
        on_tick: Callable[[Quote], None] | None = None,
    ) -> Subscription:
        """Subscribe to real-time quote updates via DhanMarketFeed.

        Creates and starts the market feed lazily on first call.
        Callbacks are wrapped to convert MarketTickEvent → Quote.
        """
        feed = await self._ensure_market_feed()

        # Wrap tick callback for MarketTickEvent → Quote conversion
        if on_tick is not None:
            def _tick_to_quote(event: MarketTickEvent) -> None:
                on_tick(Quote(symbol=event.symbol, ltp=Decimal(str(event.ltp))))
            if feed._orchestrator is not None:
                feed._orchestrator.set_callbacks(on_tick=_tick_to_quote)

        async def _cancel() -> None:
            for inst in instruments:
                sid = self._resolve_security_id(inst)
                key = InstrumentKey(
                    symbol=inst.symbol, exchange=inst.exchange.value, security_id=sid,
                )
                await feed.unsubscribe(key)

        sub = Subscription(Subscription.create_id(), _cancel)

        for inst in instruments:
            sid = self._resolve_security_id(inst)
            key = InstrumentKey(
                symbol=inst.symbol, exchange=inst.exchange.value, security_id=sid,
            )
            await feed.subscribe(key, mode=StreamMode.QUOTE)

        return sub

    async def subscribe_depth(
        self,
        instruments: list[Instrument],
        *,
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> Subscription:
        """Subscribe to real-time depth updates via DhanDepth20Feed.

        Creates and starts the depth feed lazily on first call.
        """
        feed = await self._ensure_depth_feed()

        if on_depth is not None:
            def _event_to_depth(event: MarketTickEvent) -> None:
                from brokers.domain.values import DepthLevel

                on_depth(MarketDepth(
                    symbol=event.symbol,
                    bids=[DepthLevel(price=Decimal(str(b[0])), quantity=int(b[1]))
                          for b in (event.depth_bids or ())],
                    asks=[DepthLevel(price=Decimal(str(a[0])), quantity=int(a[1]))
                          for a in (event.depth_asks or ())],
                    depth_type="DEPTH_20",
                ))

            # Depth feed callback is set via _on_depth attribute (constructor param alternative)
            feed._on_depth = _event_to_depth

        async def _cancel() -> None:
            for inst in instruments:
                sid = self._resolve_security_id(inst)
                key = InstrumentKey(
                    symbol=inst.symbol, exchange=inst.exchange.value, security_id=sid,
                )
                await feed.unsubscribe(key)

        sub = Subscription(Subscription.create_id(), _cancel)

        for inst in instruments:
            sid = self._resolve_security_id(inst)
            key = InstrumentKey(
                symbol=inst.symbol, exchange=inst.exchange.value, security_id=sid,
            )
            await feed.subscribe(key)

        return sub

    async def subscribe_orders(
        self,
        *,
        on_update: Callable[[Any], None] | None = None,
    ) -> Subscription:
        """Subscribe to order status updates via DhanOrderFeed.

        Creates and starts the order feed lazily on first call.
        """
        feed = await self._ensure_order_feed()

        if on_update is not None:
            if feed._orchestrator is not None:
                feed._orchestrator.set_callbacks(on_order=on_update)

        async def _cancel() -> None:
            await feed.stop()

        return Subscription(Subscription.create_id(), _cancel)

    async def unsubscribe(self, subscription: Subscription) -> None:
        await subscription.cancel()

    # ── Lifecycle ────────────────────────────────────────────────────

    def _build_extensions(self) -> ExtensionAccess:
        """Build ExtensionAccess with all Dhan extended capabilities."""
        from brokers.dhan.extended.alerts import DhanAlerts
        from brokers.dhan.extended.conditional_triggers import DhanConditionalTriggers
        from brokers.dhan.extended.edis import DhanEdis
        from brokers.dhan.extended.exit_all import DhanExitAll
        from brokers.dhan.extended.forever_orders import DhanForeverOrders
        from brokers.dhan.extended.ip_management import DhanIpManagement
        from brokers.dhan.extended.ledger import DhanLedger
        from brokers.dhan.extended.margin import DhanMargin
        from brokers.dhan.extended.super_orders import DhanSuperOrders
        from brokers.dhan.extended.user_profile import DhanUserProfile

        return ExtensionAccess(
            self,
            extensions={
                "alerts": DhanAlerts(client=self._client),
                "conditional_triggers": DhanConditionalTriggers(client=self._client),
                "edis": DhanEdis(client=self._client),
                "exit_all": DhanExitAll(client=self._client),
                "forever_orders": DhanForeverOrders(client=self._client),
                "ip_management": DhanIpManagement(client=self._client),
                "ledger": DhanLedger(client=self._client),
                "margin": DhanMargin(client=self._client),
                "super_orders": DhanSuperOrders(client=self._client),
                "user_profile": DhanUserProfile(client=self._client),
            },
        )

    async def connect(self) -> None:
        """Mark as connected. Feeds are created lazily on first subscribe."""
        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect: stop all feeds if running (thread-safe via asyncio.Lock)."""
        async with self._feed_lock:
            coros = []
            if self._market_feed is not None:
                coros.append(self._market_feed.stop())
                self._market_feed = None
            if self._order_feed is not None:
                coros.append(self._order_feed.stop())
                self._order_feed = None
            if self._depth_feed is not None:
                coros.append(self._depth_feed.stop())
                self._depth_feed = None
            if coros:
                await asyncio.gather(*coros)
            self._connected = False

    async def _ensure_market_feed(self) -> DhanMarketFeed:
        """Lazily create and start the market feed (thread-safe via asyncio.Lock)."""
        async with self._feed_lock:
            if self._market_feed is None or not self._market_feed.is_running:
                from brokers.dhan.streaming.market_feed import DhanMarketFeed

                self._market_feed = DhanMarketFeed(
                    client_id=self._client.client_id,
                    access_token=self._client._session.headers.get("access-token", ""),
                )
                await self._market_feed.start()
            return self._market_feed

    async def _ensure_order_feed(self) -> DhanOrderFeed:
        """Lazily create and start the order feed (thread-safe via asyncio.Lock)."""
        async with self._feed_lock:
            if self._order_feed is None or not self._order_feed.is_running:
                from brokers.dhan.streaming.order_feed import DhanOrderFeed

                self._order_feed = DhanOrderFeed(
                    client_id=self._client.client_id,
                    access_token=self._client._session.headers.get("access-token", ""),
                )
                await self._order_feed.start()
            return self._order_feed

    async def _ensure_depth_feed(self) -> DhanDepth20Feed:
        """Lazily create and start the depth feed (thread-safe via asyncio.Lock)."""
        async with self._feed_lock:
            if self._depth_feed is None or not self._depth_feed.is_running:
                from brokers.dhan.streaming.depth_feed import DhanDepth20Feed

                self._depth_feed = DhanDepth20Feed(
                    client_id=self._client.client_id,
                    access_token=self._client._session.headers.get("access-token", ""),
                )
                await self._depth_feed.start()
            return self._depth_feed


__all__ = ["DhanProvider"]

"""Upstox provider — implements the unified Provider protocol for Upstox.

Adapts the existing UpstoxHttpClient and UpstoxMapper to the new
:class:`Provider` protocol.

Usage::

    from brokers import Broker
    broker = Broker.upstox(access_token="tok")
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
from brokers.common.instrument_resolver import InstrumentNotFoundError
from brokers.upstox.client import UpstoxHttpClient
from brokers.upstox.mapper import UpstoxMapper

if TYPE_CHECKING:
    from brokers.common.instrument_resolver import InstrumentResolver
    from brokers.upstox.streaming.market_feed import UpstoxMarketFeed
    from brokers.upstox.streaming.portfolio_feed import UpstoxPortfolioStream

# ── Segment mapping ────────────────────────────────────────────────────────

_EXCHANGE_TO_SEGMENT: dict[str, str] = {
    "NSE": "NSE_EQ",
    "BSE": "BSE_EQ",
    "NFO": "NSE_FO",
    "MCX": "MCX_FO",
    "INDEX": "NSE_INDEX",
}


def _segment_for(exchange: Exchange) -> str:
    return _EXCHANGE_TO_SEGMENT.get(exchange.value, "NSE_EQ")


def _instrument_key(symbol: str, exchange: Exchange) -> str:
    """Build Upstox instrument_key from symbol + exchange."""
    segment = _segment_for(exchange)
    return f"{segment}|{symbol}"


_INTERVAL_MAP: dict[str, str] = {
    "1d": "1_day",
    "1h": "1_hour",
    "5m": "5_minute",
    "15m": "15_minute",
    "30m": "30_minute",
}


def _dec(val: Any) -> Decimal | None:
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except (ValueError, TypeError):
        return None


class UpstoxProvider:
    """Upstox broker provider implementing the Provider protocol.

    Each method: resolve instrument → call HTTP client → map response →
    return domain entity.
    """

    __slots__ = (
        "_account",
        "_client",
        "_connected",
        "_extensions",
        "_feed_lock",
        "_instruments",
        "_market_feed",
        "_resolver",
        "_portfolio_stream",
    )

    def __init__(
        self,
        *,
        access_token: str,
        instruments: dict[str, str] | None = None,
        resolver: InstrumentResolver | None = None,
        **kwargs: Any,
    ) -> None:
        self._client = UpstoxHttpClient(access_token=access_token, **kwargs)
        self._instruments: dict[str, str] = instruments or {}
        self._resolver = resolver
        self._connected = False
        self._account: Account | None = None
        self._feed_lock = asyncio.Lock()

        # Streaming feeds (created lazily on first subscribe, stopped in disconnect())
        self._market_feed: UpstoxMarketFeed | None = None
        self._portfolio_stream: UpstoxPortfolioStream | None = None

        # Extended capabilities
        self._extensions = self._build_extensions()

    # ── Identity ─────────────────────────────────────────────────────

    @property
    def broker_id(self) -> str:
        return "upstox"

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities.full("upstox", max_depth_levels=30)

    @property
    def default_account(self) -> Account:
        if self._account is None:
            self._account = Account("upstox_default", self)
        return self._account

    @property
    def extensions(self) -> ExtensionAccess:
        return self._extensions

    def update_token(self, new_token: str) -> None:
        """Hot-swap the Bearer token in the underlying HTTP client.

        Called by the :class:`AuthManager` token receiver when a
        background scheduler refreshes the token.
        """
        self._client.update_token(new_token)

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def stream_health(self) -> StreamHealth:
        """Aggregate health of all streaming feeds."""
        feeds = [
            f for f in (self._market_feed, self._portfolio_stream)
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

    def _resolve_instrument_key(self, instrument: Instrument) -> str:
        """Resolve instrument to Upstox instrument_key."""
        if instrument.security_id:
            return instrument.security_id
        key = f"{instrument.symbol}:{instrument.exchange.value}"
        inst_key = self._instruments.get(key)
        if inst_key:
            return inst_key
        if self._resolver is not None:
            try:
                resolved = self._resolver.resolve(instrument.symbol, instrument.exchange)
                return resolved.broker_id
            except InstrumentNotFoundError:
                pass
        return _instrument_key(instrument.symbol, instrument.exchange)

    # ── Market data ──────────────────────────────────────────────────

    async def get_quote(self, instrument: Instrument) -> Quote:
        inst_key = self._resolve_instrument_key(instrument)
        data = self._client.get_quote([inst_key])
        raw = data.get("data", {}).get(inst_key, {})
        if not raw:
            raise ProviderError(f"No quote data for {instrument.symbol}")
        return UpstoxMapper.map_quote(raw, instrument.symbol)

    async def get_ltp(self, instrument: Instrument) -> Decimal:
        inst_key = self._resolve_instrument_key(instrument)
        data = self._client.get_ltp([inst_key])
        raw = data.get("data", {}).get(inst_key, {})
        if not raw:
            raise ProviderError(f"No LTP data for {instrument.symbol}")
        return Decimal(str(raw.get("last_price", 0)))

    async def get_depth(self, instrument: Instrument) -> MarketDepth:
        inst_key = self._resolve_instrument_key(instrument)
        data = self._client.get_quote([inst_key])
        raw = data.get("data", {}).get(inst_key, {})
        if not raw:
            raise ProviderError(f"No depth data for {instrument.symbol}")
        return UpstoxMapper.map_depth(raw, instrument.symbol)

    async def get_history(
        self,
        instrument: Instrument,
        *,
        timeframe: str = "1D",
        bars: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> HistoricalSeries:
        inst_key = self._resolve_instrument_key(instrument)
        interval = _INTERVAL_MAP.get(timeframe.lower(), timeframe.lower())
        from_str = str(from_date) if from_date else "2026-01-01"
        to_str = str(to_date) if to_date else "2026-06-30"
        data = self._client.get_historical_candles(inst_key, interval, from_str, to_str)
        candles = data.get("data", {}).get("candles", [])
        candles = candles if isinstance(candles, list) else []

        bar_list: list[HistoricalBar] = []

        for item in candles:
            if isinstance(item, list) and len(item) >= 5:
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
        for key, inst_key in self._instruments.items():
            symbol = key.split(":")[0]
            if q in symbol.upper():
                exchange_str = key.split(":")[1] if ":" in key else "NSE"
                search_results.append(Instrument(
                    symbol=symbol,
                    exchange=Exchange(exchange_str),
                    provider=self,
                    security_id=inst_key,
                ))
                if len(search_results) >= 20:
                    break
        return search_results

    async def get_instruments(self, exchange: str | None = None) -> list[Instrument]:
        results: list[Instrument] = []
        for key, inst_key in self._instruments.items():
            parts = key.split(":")
            symbol = parts[0]
            exchange_str = parts[1] if len(parts) > 1 else "NSE"
            if exchange is None or exchange_str == exchange:
                results.append(Instrument(
                    symbol=symbol,
                    exchange=Exchange(exchange_str),
                    provider=self,
                    security_id=inst_key,
                ))
        return results

    async def resolve_instrument(self, symbol: str, exchange: str) -> Instrument:
        key = f"{symbol}:{exchange}"
        inst_key = self._instruments.get(key, _instrument_key(symbol, Exchange(exchange)))
        lot_size = 1
        tick_size = Decimal("0.05")
        trading_symbol = ""
        if self._resolver is not None:
            try:
                resolved = self._resolver.resolve(symbol, Exchange(exchange))
                inst_key = resolved.broker_id
                lot_size = resolved.lot_size
                tick_size = resolved.tick_size
                trading_symbol = resolved.trading_symbol
            except InstrumentNotFoundError:
                pass
        return Instrument(
            symbol=symbol,
            exchange=Exchange(exchange),
            provider=self,
            security_id=inst_key,
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
        inst_key = self._resolve_instrument_key(underlying)
        exp = str(expiry) if expiry else ""
        data = self._client.get_option_chain(inst_key, exp)

        # Parse Upstox option chain response
        raw_chain: dict[str, Any] | list[Any] = data.get("data") or {}
        contracts: list[OptionContract] = []

        if isinstance(raw_chain, dict):
            for strike_data in raw_chain.get("strikes", raw_chain.get("data", [])):  # type: ignore[union-attr]
                if isinstance(strike_data, dict):
                    strike_val = Decimal(str(strike_data.get("strike", strike_data.get("strikePrice", 0))))
                    exp_date = expiry or date.today()

                    call_data = strike_data.get("call", strike_data.get("CE", {}))
                    if call_data:
                        contracts.append(OptionContract(
                            strike=strike_val,
                            option_type=OptionType.CALL,
                            expiry=exp_date,
                            symbol=str(call_data.get("symbol", call_data.get("tradingSymbol", ""))),
                            ltp=_dec(call_data.get("ltp")),
                            oi=int(call_data.get("oi", 0)) if call_data.get("oi") else None,
                            volume=int(call_data.get("volume", 0)) if call_data.get("volume") else None,
                        ))

                    put_data = strike_data.get("put", strike_data.get("PE", {}))
                    if put_data:
                        contracts.append(OptionContract(
                            strike=strike_val,
                            option_type=OptionType.PUT,
                            expiry=exp_date,
                            symbol=str(put_data.get("symbol", put_data.get("tradingSymbol", ""))),
                            ltp=_dec(put_data.get("ltp")),
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
        return FutureChain(underlying=underlying, contracts=[])

    # ── Execution ────────────────────────────────────────────────────

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        try:
            key = f"{request.symbol}:{request.exchange.value}"
            inst_key = self._instruments.get(key, _instrument_key(request.symbol, request.exchange))
            payload = UpstoxMapper.build_order_payload(request, inst_key)
            data = self._client.place_order(payload)
            order_id = ""
            if isinstance(data, dict):
                order_id = str(data.get("data", {}).get("order_id", data.get("order_id", "")))
            return OrderResponse.ok(order_id=order_id, message="Order placed", status=OrderStatus.OPEN)
        except HttpError as exc:
            return OrderResponse.fail(str(exc), error_code="UPSTOX_HTTP_ERROR")
        except Exception as exc:
            return OrderResponse.fail(str(exc), error_code="INTERNAL_ERROR")

    async def cancel_order(self, order_id: str) -> OrderResponse:
        try:
            data = self._client.cancel_order(order_id)
            if isinstance(data, dict) and data.get("status", "").lower() == "success":
                return OrderResponse.ok(order_id=order_id, message="Order cancelled", status=OrderStatus.CANCELLED)
            return OrderResponse.fail(
                str(data.get("message", "Cancel failed")) if isinstance(data, dict) else "Cancel failed",
                error_code="UPSTOX_CANCEL_FAILED",
            )
        except HttpError as exc:
            return OrderResponse.fail(str(exc), error_code="UPSTOX_HTTP_ERROR")

    async def modify_order(self, request: ModifyOrderRequest) -> OrderResponse:
        try:
            payload = {k: v for k, v in {
                "quantity": request.quantity,
                "price": request.price,
                "trigger_price": request.trigger_price,
                "order_type": request.order_type.value if request.order_type else None,
                "validity": request.validity.value if request.validity else None,
                "product": request.product_type.value if request.product_type else None,
            }.items() if v is not None}
            data = self._client.modify_order(request.order_id, payload)
            if isinstance(data, dict) and data.get("status", "").lower() == "success":
                return OrderResponse.ok(order_id=request.order_id, message="Order modified")
            return OrderResponse.fail(
                str(data.get("message", "Modify failed")) if isinstance(data, dict) else "Modify failed",
                error_code="UPSTOX_MODIFY_FAILED",
            )
        except HttpError as exc:
            return OrderResponse.fail(str(exc), error_code="UPSTOX_HTTP_ERROR")

    # ── Portfolio ────────────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        data = self._client.get_positions()
        items = data.get("data", []) if isinstance(data, dict) else []
        return [UpstoxMapper.map_position(item) for item in (items if isinstance(items, list) else [])]

    async def get_balance(self) -> Balance:
        data = self._client.get_funds()
        raw = data.get("data", data) if isinstance(data, dict) else {}
        if isinstance(raw, dict) and "equity" in raw:
            raw = raw["equity"]
        return UpstoxMapper.map_balance(raw if isinstance(raw, dict) else {})

    async def get_orders(self) -> list[Any]:
        data = self._client.get_orderbook()
        items = data.get("data", []) if isinstance(data, dict) else []
        return [UpstoxMapper.map_order(item) for item in (items if isinstance(items, list) else [])]

    async def get_trades(self) -> list[Trade]:
        data = self._client.get_trades()
        items = data.get("data", []) if isinstance(data, dict) else []
        return [UpstoxMapper.map_trade(item) for item in (items if isinstance(items, list) else [])]

    async def get_holdings(self) -> list[Holding]:
        data = self._client.get_holdings()
        items = data.get("data", []) if isinstance(data, dict) else []
        return [UpstoxMapper.map_holding(item) for item in (items if isinstance(items, list) else [])]

    # ── Streaming ────────────────────────────────────────────────────

    async def subscribe_quotes(
        self,
        instruments: list[Instrument],
        *,
        on_tick: Callable[[Quote], None] | None = None,
    ) -> Subscription:
        """Subscribe to real-time quote updates via UpstoxMarketFeed.

        Creates and starts the market feed lazily on first call.
        """
        feed = await self._ensure_market_feed()

        if on_tick is not None:
            def _tick_to_quote(event: MarketTickEvent) -> None:
                on_tick(Quote(symbol=event.symbol, ltp=Decimal(str(event.ltp))))
            if feed._orchestrator is not None:
                feed._orchestrator.set_callbacks(on_tick=_tick_to_quote)

        async def _cancel() -> None:
            for inst in instruments:
                inst_key = self._resolve_instrument_key(inst)
                key = InstrumentKey(
                    symbol=inst.symbol, exchange=inst.exchange.value, security_id=inst_key,
                )
                await feed.unsubscribe(key)

        sub = Subscription(Subscription.create_id(), _cancel)

        for inst in instruments:
            inst_key = self._resolve_instrument_key(inst)
            key = InstrumentKey(
                symbol=inst.symbol, exchange=inst.exchange.value, security_id=inst_key,
            )
            await feed.subscribe(key, mode=StreamMode.QUOTE)

        return sub

    async def subscribe_depth(
        self,
        instruments: list[Instrument],
        *,
        on_depth: Callable[[MarketDepth], None] | None = None,
    ) -> Subscription:
        """Subscribe to real-time depth updates via UpstoxMarketFeed (D30 mode).

        Creates and starts the market feed lazily on first call.
        """
        feed = await self._ensure_market_feed()

        if on_depth is not None:
            def _event_to_depth(event: MarketTickEvent) -> None:
                from brokers.domain.values import DepthLevel

                on_depth(MarketDepth(
                    symbol=event.symbol,
                    bids=[DepthLevel(price=Decimal(str(b[0])), quantity=int(b[1]))
                          for b in (event.depth_bids or ())],
                    asks=[DepthLevel(price=Decimal(str(a[0])), quantity=int(a[1]))
                          for a in (event.depth_asks or ())],
                    depth_type="DEPTH_30",
                ))

            if feed._orchestrator is not None:
                feed._orchestrator.set_callbacks(on_tick=_event_to_depth)

        async def _cancel() -> None:
            for inst in instruments:
                inst_key = self._resolve_instrument_key(inst)
                key = InstrumentKey(
                    symbol=inst.symbol, exchange=inst.exchange.value, security_id=inst_key,
                )
                await feed.unsubscribe(key)

        sub = Subscription(Subscription.create_id(), _cancel)

        for inst in instruments:
            inst_key = self._resolve_instrument_key(inst)
            key = InstrumentKey(
                symbol=inst.symbol, exchange=inst.exchange.value, security_id=inst_key,
            )
            await feed.subscribe(key, mode=StreamMode.DEPTH)

        return sub

    async def subscribe_orders(
        self,
        *,
        on_update: Callable[[Any], None] | None = None,
    ) -> Subscription:
        """Subscribe to order status updates via UpstoxPortfolioStream.

        Creates and starts the portfolio stream lazily on first call.
        """
        feed = await self._ensure_portfolio_stream()

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
        """Build ExtensionAccess with all Upstox extended capabilities."""
        from brokers.upstox.extended.alerts import UpstoxAlerts
        from brokers.upstox.extended.cover_order import UpstoxCoverOrders
        from brokers.upstox.extended.exit_all import UpstoxExitAll
        from brokers.upstox.extended.expired_instruments import UpstoxExpiredInstruments
        from brokers.upstox.extended.fundamentals import UpstoxFundamentals
        from brokers.upstox.extended.gtt import UpstoxGTT
        from brokers.upstox.extended.ipo import UpstoxIPO
        from brokers.upstox.extended.kill_switch import UpstoxKillSwitch
        from brokers.upstox.extended.margin import UpstoxMargin
        from brokers.upstox.extended.market_intelligence import UpstoxMarketIntelligence
        from brokers.upstox.extended.market_status import UpstoxMarketStatus
        from brokers.upstox.extended.mutual_funds import UpstoxMutualFunds
        from brokers.upstox.extended.news import UpstoxNews
        from brokers.upstox.extended.order_query import UpstoxOrderQuery
        from brokers.upstox.extended.payments import UpstoxPayments
        from brokers.upstox.extended.reconciliation import UpstoxReconciliation
        from brokers.upstox.extended.slice import UpstoxSliceOrders
        from brokers.upstox.extended.static_ip import UpstoxStaticIp

        return ExtensionAccess(
            self,
            extensions={
                "alerts": UpstoxAlerts(client=self._client),
                "cover_order": UpstoxCoverOrders(client=self._client),
                "exit_all": UpstoxExitAll(client=self._client),
                "expired_instruments": UpstoxExpiredInstruments(client=self._client),
                "fundamentals": UpstoxFundamentals(client=self._client),
                "gtt": UpstoxGTT(client=self._client),
                "ipo": UpstoxIPO(client=self._client),
                "kill_switch": UpstoxKillSwitch(client=self._client),
                "margin": UpstoxMargin(client=self._client),
                "market_intelligence": UpstoxMarketIntelligence(client=self._client),
                "market_status": UpstoxMarketStatus(client=self._client),
                "mutual_funds": UpstoxMutualFunds(client=self._client),
                "news": UpstoxNews(client=self._client),
                "order_query": UpstoxOrderQuery(client=self._client),
                "payments": UpstoxPayments(client=self._client),
                "reconciliation": UpstoxReconciliation(client=self._client),
                "slice": UpstoxSliceOrders(client=self._client),
                "static_ip": UpstoxStaticIp(client=self._client),
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
            if self._portfolio_stream is not None:
                coros.append(self._portfolio_stream.stop())
                self._portfolio_stream = None
            if coros:
                await asyncio.gather(*coros)
            self._connected = False

    async def _ensure_market_feed(self) -> UpstoxMarketFeed:
        """Lazily create and start the market feed (thread-safe via asyncio.Lock)."""
        async with self._feed_lock:
            if self._market_feed is None or not self._market_feed.is_running:
                from brokers.upstox.streaming.market_feed import UpstoxMarketFeed

                self._market_feed = UpstoxMarketFeed(http_client=self._client)
                await self._market_feed.start()
            return self._market_feed

    async def _ensure_portfolio_stream(self) -> UpstoxPortfolioStream:
        """Lazily create and start the portfolio stream (thread-safe via asyncio.Lock)."""
        async with self._feed_lock:
            if self._portfolio_stream is None or not self._portfolio_stream.is_running:
                from brokers.upstox.streaming.portfolio_feed import UpstoxPortfolioStream

                self._portfolio_stream = UpstoxPortfolioStream(http_client=self._client)
                await self._portfolio_stream.start()
            return self._portfolio_stream


__all__ = ["UpstoxProvider"]

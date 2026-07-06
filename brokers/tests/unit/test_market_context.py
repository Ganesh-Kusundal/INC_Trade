"""Unit tests for Market Data Context components.

Covers:
- QuoteState (update, snapshot, staleness, spread, vwap)
- DepthState (update, snapshot, best_bid/ask, spread, staleness)
- MarketDataContext (delegation to ports, backward compat aliases)
- InstrumentHandle (delegation to Instrument + context methods)
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from inc_trade.domain.entities import MarketDepth, Quote
from inc_trade.market.context import InstrumentHandle, MarketDataContext
from inc_trade.market.depth_state import DepthLevelState, DepthState
from inc_trade.market.instrument import Instrument
from inc_trade.market.instrument_registry import InstrumentRegistry
from inc_trade.market.market_router import MarketRouter
from inc_trade.market.quote_state import QuoteState

# ═══════════════════════════════════════════════════════════════
# QuoteState tests
# ═══════════════════════════════════════════════════════════════


class TestQuoteState:
    def test_default_ltp_zero(self) -> None:
        state = QuoteState(composite_key="NSE:RELIANCE")
        assert state.ltp == Decimal("0")

    def test_update_from_quote_entity(self) -> None:
        state = QuoteState(composite_key="NSE:RELIANCE")
        quote = Quote(symbol="RELIANCE", ltp=Decimal("2500.50"), exchange="NSE")
        state.update_from_quote(quote)
        assert state.ltp == Decimal("2500.50")

    def test_update_from_dict(self) -> None:
        state = QuoteState(composite_key="NSE:RELIANCE")
        state.update_from_quote({"ltp": "2510.75", "volume": 50000})
        assert state.ltp == Decimal("2510.75")
        assert state.volume == 50000

    def test_update_from_dict_max_high(self) -> None:
        state = QuoteState(composite_key="NSE:RELIANCE")
        state.high = Decimal("2520")
        state.update_from_quote({"high": "2530"})
        assert state.high == Decimal("2530")

    def test_update_from_dict_min_low(self) -> None:
        state = QuoteState(composite_key="NSE:RELIANCE")
        state.low = Decimal("2500")
        state.update_from_quote({"low": "2490"})
        assert state.low == Decimal("2490")

    def test_snapshot_returns_quote(self) -> None:
        state = QuoteState(composite_key="NSE:RELIANCE", ltp=Decimal("2500"))
        snap = state.snapshot()
        assert isinstance(snap, Quote)
        assert snap.symbol == "RELIANCE"
        assert snap.ltp == Decimal("2500")

    def test_is_stale_when_no_timestamp(self) -> None:
        state = QuoteState(composite_key="NSE:RELIANCE")
        assert state.is_stale() is True

    def test_is_stale_when_recent(self) -> None:
        state = QuoteState(composite_key="NSE:RELIANCE")
        state.timestamp = datetime.now(UTC)
        assert state.is_stale(max_age_seconds=60) is False

    def test_is_stale_when_expired(self) -> None:
        state = QuoteState(composite_key="NSE:RELIANCE")
        # Set timestamp to well in the past
        state.timestamp = datetime(2020, 1, 1, tzinfo=UTC)
        assert state.is_stale(max_age_seconds=1) is True

    def test_spread_zero_when_no_bid_ask(self) -> None:
        state = QuoteState(composite_key="NSE:RELIANCE")
        assert state.spread == Decimal("0")

    def test_spread_calculation(self) -> None:
        state = QuoteState(composite_key="NSE:RELIANCE", bid=Decimal("100"), ask=Decimal("101"))
        assert state.spread == Decimal("1")

    def test_vwap_fallback_to_ltp(self) -> None:
        state = QuoteState(composite_key="NSE:RELIANCE", ltp=Decimal("2500"))
        assert state.vwap == Decimal("2500")

    def test_seq_no_increments_on_update(self) -> None:
        state = QuoteState(composite_key="NSE:RELIANCE", seq_no=0)
        state.update_from_quote({"ltp": "2500"})
        assert state.seq_no == 1
        state.update_from_quote({"ltp": "2501"})
        assert state.seq_no == 2


# ═══════════════════════════════════════════════════════════════
# DepthState tests
# ═══════════════════════════════════════════════════════════════


class TestDepthLevelState:
    def test_snapshot_returns_depth_level(self) -> None:
        from inc_trade.domain.entities import DepthLevel

        level = DepthLevelState(price=Decimal("100"), quantity=1000, orders=5)
        snap = level.snapshot()
        assert isinstance(snap, DepthLevel)
        assert snap.price == Decimal("100")
        assert snap.quantity == 1000
        assert snap.orders == 5


class TestDepthState:
    def test_default_state(self) -> None:
        state = DepthState(composite_key="NSE:RELIANCE")
        assert state.bids == []
        assert state.asks == []

    def test_update_from_depth(self) -> None:
        state = DepthState(composite_key="NSE:RELIANCE")
        bids = [{"price": "100", "quantity": 1000, "orders": 5}]
        asks = [{"price": "101", "quantity": 800, "orders": 3}]
        state.update_from_depth(bids=bids, asks=asks)
        assert len(state.bids) == 1
        assert state.bids[0].price == Decimal("100")
        assert len(state.asks) == 1
        assert state.asks[0].price == Decimal("101")

    def test_best_bid(self) -> None:
        state = DepthState(composite_key="NSE:RELIANCE")
        state.update_from_depth(
            bids=[
                {"price": "99", "quantity": 100},
                {"price": "100", "quantity": 200},
                {"price": "98", "quantity": 150},
            ]
        )
        bb = state.best_bid
        assert bb is not None
        assert bb.price == Decimal("100")

    def test_best_ask(self) -> None:
        state = DepthState(composite_key="NSE:RELIANCE")
        state.update_from_depth(
            asks=[
                {"price": "101", "quantity": 200},
                {"price": "102", "quantity": 100},
                {"price": "103", "quantity": 150},
            ]
        )
        ba = state.best_ask
        assert ba is not None
        assert ba.price == Decimal("101")

    def test_spread(self) -> None:
        state = DepthState(composite_key="NSE:RELIANCE")
        state.update_from_depth(
            bids=[{"price": "100", "quantity": 1000}],
            asks=[{"price": "101", "quantity": 800}],
        )
        assert state.spread == Decimal("1")

    def test_spread_zero_when_no_data(self) -> None:
        state = DepthState(composite_key="NSE:RELIANCE")
        assert state.spread == Decimal("0")

    def test_snapshot_returns_market_depth(self) -> None:
        state = DepthState(composite_key="NSE:RELIANCE")
        state.update_from_depth(
            bids=[{"price": "100", "quantity": 1000}],
            asks=[{"price": "101", "quantity": 800}],
        )
        snap = state.snapshot()
        assert isinstance(snap, MarketDepth)
        assert snap.symbol == "RELIANCE"
        assert len(snap.bids) == 1
        assert len(snap.asks) == 1

    def test_is_stale_when_no_timestamp(self) -> None:
        state = DepthState(composite_key="NSE:RELIANCE")
        assert state.is_stale() is True

    def test_is_stale_when_recent(self) -> None:
        state = DepthState(composite_key="NSE:RELIANCE")
        state.timestamp = datetime.now(UTC)
        assert state.is_stale(max_age_seconds=60) is False


# ═══════════════════════════════════════════════════════════════
# MarketDataContext tests
# ═══════════════════════════════════════════════════════════════


class _FakeMarketData:
    """Minimal MarketDataPort fake for testing."""

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        return Decimal("100.00")

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        return Quote(symbol=symbol, ltp=Decimal("100.00"), exchange=exchange)

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        return MarketDepth(symbol=symbol, exchange=exchange)

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        return {s: Decimal("100.00") for s in symbols}

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        return {s: Quote(symbol=s, ltp=Decimal("100.00"), exchange=exchange) for s in symbols}


class _FakeHistorical:
    """Minimal HistoricalPort fake for testing."""

    def __init__(self) -> None:
        self.call_count = 0

    def get_historical_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list:
        self.call_count += 1
        return []


class _FakeOptions:
    """Minimal OptionsPort fake for testing."""

    def get_expiries(self, underlying: str, exchange: str = "NFO") -> list[str]:
        return ["2024-01-25", "2024-02-22"]

    def get_option_chain(
        self, underlying: str, exchange: str = "NFO", expiry: str | None = None
    ) -> OptionChain:
        from inc_trade.domain.entities import OptionChain

        return OptionChain(
            underlying=underlying, expiry=expiry or "2024-01-25", spot=Decimal("20000"), strikes=()
        )


class _FakeStreaming:
    """Minimal StreamingPort fake for testing.

    Supports both the legacy async ``subscribe_quotes`` protocol and the
    new synchronous ``subscribe(key, exchange)`` protocol used by
    ``SubscriptionManager``.
    """

    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self._connected = True

    # SubscriptionManager protocol (synchronous)
    def subscribe(self, key: str, exchange: str) -> None:
        self.subscribed.append(key)

    def unsubscribe(self, key: str, exchange: str) -> None:
        self.unsubscribed.append(key)

    async def connect(self) -> None:
        pass

    async def disconnect(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def subscribe_quotes(self, symbols: list[str], exchange: str, callback) -> None:
        self.subscribed.extend(symbols)

    async def unsubscribe_quotes(self, symbols: list[str], exchange: str) -> None:
        self.unsubscribed.extend(symbols)


@pytest.fixture
def registry() -> InstrumentRegistry:
    reg = InstrumentRegistry()
    inst = Instrument(
        symbol="RELIANCE", exchange="NSE", segment="NSE_EQ", name="Reliance Industries", lot_size=1
    )
    reg.get_or_create("NSE:RELIANCE", lambda: inst)
    return reg


@pytest.fixture
def context(registry: InstrumentRegistry) -> MarketDataContext:
    return MarketDataContext(
        registry=registry,
        market_data=_FakeMarketData(),
        historical=_FakeHistorical(),
        options=_FakeOptions(),
        streaming=_FakeStreaming(),
    )


class TestMarketDataContext:
    def test_instrument_returns_instrument_handle(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        assert isinstance(handle, InstrumentHandle)

    def test_instrument_raises_key_error_for_missing(self, context: MarketDataContext) -> None:
        with pytest.raises(KeyError):
            context.instrument("UNKNOWN")

    def test_quote_delegates(self, context: MarketDataContext) -> None:
        q = context.quote("RELIANCE")
        assert isinstance(q, Quote)
        assert q.ltp == Decimal("100.00")

    def test_ltp_delegates(self, context: MarketDataContext) -> None:
        price = context.ltp("RELIANCE")
        assert price == Decimal("100.00")

    def test_ltp_batch_delegates(self, context: MarketDataContext) -> None:
        prices = context.ltp_batch(["RELIANCE", "TCS"])
        assert prices == {"RELIANCE": Decimal("100.00"), "TCS": Decimal("100.00")}

    def test_quote_batch_delegates(self, context: MarketDataContext) -> None:
        quotes = context.quote_batch(["RELIANCE"])
        assert isinstance(quotes["RELIANCE"], Quote)

    def test_depth_delegates(self, context: MarketDataContext) -> None:
        d = context.depth("RELIANCE")
        assert isinstance(d, MarketDepth)
        assert d.symbol == "RELIANCE"

    def test_ohlcv_delegates(self, context: MarketDataContext) -> None:
        from datetime import datetime

        candles = context.ohlcv("RELIANCE", "NSE", datetime(2024, 1, 1), datetime(2024, 1, 2), "1")
        assert candles == []

    def test_option_chain_delegates(self, context: MarketDataContext) -> None:
        chain = context.option_chain("RELIANCE", exchange="NFO")
        # underlying is an Instrument object (Phase 3+)
        assert chain.underlying is not None
        assert chain.expiry == "2024-01-25"

    def test_expiries_delegates(self, context: MarketDataContext) -> None:
        expiries = context.expiries("RELIANCE", exchange="NFO")
        assert "2024-01-25" in expiries

    # ── Canonical method names (replace old get_* aliases) ─────────────

    def test_quote_method(self, context: MarketDataContext) -> None:
        q = context.quote("RELIANCE")
        assert isinstance(q, Quote)
        assert q.ltp == Decimal("100.00")

    def test_ohlcv_method(self, context: MarketDataContext) -> None:
        from datetime import datetime

        candles = context.ohlcv("RELIANCE", "NSE", datetime(2024, 1, 1), datetime(2024, 1, 2), "1")
        assert candles == []

    # ── NotSupported errors ────────────────────────────────────────────

    def test_ohlcv_raises_not_supported_when_no_historical(
        self, registry: InstrumentRegistry
    ) -> None:
        from inc_trade.domain.exceptions import NotSupportedError

        ctx = MarketDataContext(registry=registry, market_data=_FakeMarketData())
        with pytest.raises(NotSupportedError):
            ctx.ohlcv("RELIANCE", "NSE", datetime(2024, 1, 1), datetime(2024, 1, 2), "1")

    def test_option_chain_raises_not_supported_when_no_options(
        self, registry: InstrumentRegistry
    ) -> None:
        from inc_trade.domain.exceptions import NotSupportedError

        ctx = MarketDataContext(registry=registry, market_data=_FakeMarketData())
        with pytest.raises(NotSupportedError):
            ctx.option_chain("RELIANCE")

    # ── Streaming → Cache Invalidation ─────────────────────────────────

    def test_streaming_tick_invalidates_market_router_cache(self) -> None:
        """When a streaming tick arrives, MarketRouter cache must be
        invalidated so the next quote() call fetches fresh data."""
        from inc_trade.infrastructure.cache.memory_cache import MemoryCache
        from inc_trade.market.subscription_manager import SubscriptionManager

        cache = MemoryCache()
        market_router = MarketRouter(cache=cache, primary=_FakeMarketData())
        streaming = _FakeStreaming()
        sub_mgr = SubscriptionManager(stream_adapter=streaming)

        ctx = MarketDataContext(
            registry=InstrumentRegistry(),
            market_data=_FakeMarketData(),
            market_router=market_router,
            subscription_manager=sub_mgr,
        )

        # Prime the cache with a quote
        ctx.quote("RELIANCE")
        # Verify cache is populated
        cached = cache.get("quote:NSE:RELIANCE")
        assert cached is not None

        # Simulate a streaming tick arriving
        captured: list[Quote] = []

        def on_tick(q: Quote) -> None:
            captured.append(q)

        handle = ctx.subscribe("RELIANCE", "NSE", on_tick)

        # Manually dispatch a tick through the SubscriptionManager
        tick = Quote(symbol="RELIANCE", ltp=Decimal("2500.50"), exchange="NSE")
        sub_mgr.dispatch_tick("NSE:RELIANCE", tick)

        # After tick dispatch, cache should be invalidated
        cached_after = cache.get("quote:NSE:RELIANCE")
        assert cached_after is None, "MarketRouter cache should be invalidated after streaming tick"

    def test_streaming_tick_no_market_router_does_not_crash(self) -> None:
        """When no MarketRouter is configured, streaming tick should
        not crash (regression test)."""
        from inc_trade.market.subscription_manager import SubscriptionManager

        streaming = _FakeStreaming()
        sub_mgr = SubscriptionManager(stream_adapter=streaming)

        ctx = MarketDataContext(
            registry=InstrumentRegistry(),
            market_data=_FakeMarketData(),
            subscription_manager=sub_mgr,
        )

        captured: list[Quote] = []

        def on_tick(q: Quote) -> None:
            captured.append(q)

        ctx.subscribe("RELIANCE", "NSE", on_tick)

        # Manually dispatch a tick — should not raise even with no MarketRouter
        tick = Quote(symbol="RELIANCE", ltp=Decimal("2500.50"), exchange="NSE")
        sub_mgr.dispatch_tick("NSE:RELIANCE", tick)
        assert len(captured) == 1


# ═══════════════════════════════════════════════════════════════
# InstrumentHandle tests
# ═══════════════════════════════════════════════════════════════


class TestInstrumentHandle:
    def test_delegates_symbol(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        assert handle.symbol == "RELIANCE"

    def test_delegates_exchange(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        assert handle.exchange == "NSE"

    def test_delegates_is_equity(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        assert handle.is_equity() is True

    def test_delegates_composite_key(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        assert handle.composite_key == "NSE:RELIANCE"

    def test_delegates_display_name(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        assert "RELIANCE" in handle.display_name()

    def test_quote_delegates_to_context(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        q = handle.quote()
        assert isinstance(q, Quote)
        assert q.ltp == Decimal("100.00")

    def test_depth_delegates_to_context(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        d = handle.depth()
        assert isinstance(d, MarketDepth)
        assert d.symbol == "RELIANCE"

    def test_ohlcv_delegates_to_context(self, context: MarketDataContext) -> None:
        from datetime import datetime

        handle = context.instrument("RELIANCE")
        candles = handle.ohlcv(datetime(2024, 1, 1), datetime(2024, 1, 2), "1")
        assert candles == []

    def test_option_chain_delegates_to_context(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        chain = handle.option_chain(expiry="2024-01-25")
        # underlying is an Instrument object (Phase 3+)
        assert chain.underlying is not None
        assert chain.expiry == "2024-01-25"

    def test_snapshot_returns_quote(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        snap = handle.snapshot()
        assert isinstance(snap, Quote)

    def test_repr(self, context: MarketDataContext) -> None:

        handle = context.instrument("RELIANCE")
        assert "InstrumentHandle" in repr(handle)

    def test_getattr_delegates_methods(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        assert handle.validate_price(Decimal("100")) is True
        assert handle.validate_quantity(1) is True

    def test_getattr_raises_attribute_error_for_private(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        with pytest.raises(AttributeError):
            _ = handle._private_attr


# ═══════════════════════════════════════════════════════════════
# Instrument-Centric Access tests (Phase 2)
# ═══════════════════════════════════════════════════════════════


class TestInstrumentCentric:
    """Tests for instrument-centric access — Instrument as primary abstraction.

    ``Instrument`` now exposes ``quote()``, ``depth()``, ``subscribe()``, etc.
    directly when obtained through ``MarketDataContext.instrument()``.
    These delegate to the attached ``MarketDataContext``.
    """

    def test_instrument_has_context_after_lookup(self, context: MarketDataContext) -> None:
        """Instrument obtained via MarketDataContext.instrument() has
        ``_context`` set to the MarketDataContext."""
        handle = context.instrument("RELIANCE")
        inst = handle._instrument
        assert inst._context is context

    def test_instrument_quote_delegates_to_context(self, context: MarketDataContext) -> None:
        """Instrument.quote() delegates to MarketDataContext.quote()."""
        handle = context.instrument("RELIANCE")
        inst = handle._instrument
        q = inst.quote()
        assert isinstance(q, Quote)
        assert q.ltp == Decimal("100.00")

    def test_instrument_ltp_delegates_to_context(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        inst = handle._instrument
        price = inst.ltp()
        assert price == Decimal("100.00")

    def test_instrument_depth_delegates_to_context(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        inst = handle._instrument
        d = inst.depth()
        assert isinstance(d, MarketDepth)
        assert d.symbol == "RELIANCE"

    def test_instrument_ohlcv_delegates_to_context(self, context: MarketDataContext) -> None:
        from datetime import datetime

        handle = context.instrument("RELIANCE")
        inst = handle._instrument
        candles = inst.ohlcv(datetime(2024, 1, 1), datetime(2024, 1, 2), "1")
        assert candles == []

    def test_instrument_history_alias(self, context: MarketDataContext) -> None:
        from datetime import datetime

        handle = context.instrument("RELIANCE")
        inst = handle._instrument
        candles = inst.history(datetime(2024, 1, 1), datetime(2024, 1, 2), "1")
        assert candles == []

    def test_instrument_option_chain_delegates(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        inst = handle._instrument
        chain = inst.option_chain(expiry="2024-01-25")
        # underlying is an Instrument object (Phase 3+)
        assert chain.underlying is not None
        assert chain.expiry == "2024-01-25"

    def test_instrument_snapshot_returns_quote(self, context: MarketDataContext) -> None:
        handle = context.instrument("RELIANCE")
        inst = handle._instrument
        snap = inst.snapshot()
        assert isinstance(snap, Quote)

    def test_instrument_quote_state_returns_quote_state(self, context: MarketDataContext) -> None:
        from inc_trade.market.quote_state import QuoteState

        handle = context.instrument("RELIANCE")
        inst = handle._instrument
        state = inst.quote_state()
        assert isinstance(state, QuoteState)
        assert state.composite_key == "NSE:RELIANCE"

    def test_raw_instrument_without_context_raises_runtime_error(self) -> None:
        """A raw Instrument created directly (not via MarketDataContext)
        raises RuntimeError when calling context-backed methods."""
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        assert inst._context is None
        with pytest.raises(RuntimeError, match="no market data context"):
            inst.quote()

    def test_raw_instrument_ltp_without_context_raises(self) -> None:
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        with pytest.raises(RuntimeError, match="no market data context"):
            inst.ltp()

    def test_raw_instrument_depth_without_context_raises(self) -> None:
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        with pytest.raises(RuntimeError, match="no market data context"):
            inst.depth()

    def test_raw_instrument_subscribe_without_context_raises(self) -> None:
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        with pytest.raises(RuntimeError, match="no market data context"):
            inst.subscribe(lambda q: None)

    def test_raw_instrument_unsubscribe_without_context_raises(self) -> None:
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        with pytest.raises(RuntimeError, match="no market data context"):
            inst.unsubscribe()

    def test_raw_instrument_option_chain_without_context_raises(self) -> None:
        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        with pytest.raises(RuntimeError, match="no market data context"):
            inst.option_chain()

    def test_raw_instrument_history_without_context_raises(self) -> None:
        from datetime import datetime

        from inc_trade.market.instrument import Instrument

        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        with pytest.raises(RuntimeError, match="no market data context"):
            inst.history(datetime(2024, 1, 1), datetime(2024, 1, 2), "1")


# ═══════════════════════════════════════════════════════════════
# Integration: connect() returns BrokerSession with market= context
# ═══════════════════════════════════════════════════════════════


class TestConnectIntegration:
    def test_connect_returns_broker_session_with_market_context(self) -> None:
        """Verify that connect() wires MarketDataContext into BrokerSession."""
        import brokers

        broker = brokers.connect("paper")
        try:
            # broker.market should be a MarketDataContext instance
            from inc_trade.market.context import MarketDataContext

            assert isinstance(broker.market, MarketDataContext)

            # Instrument-centric path works
            handle = broker.market.instrument("RELIANCE")
            from inc_trade.market.context import InstrumentHandle

            assert isinstance(handle, InstrumentHandle)
            assert handle.symbol == "RELIANCE"
            assert handle.exchange == "NSE"

            # Data delegation works
            q = handle.quote()
            assert q.symbol == "RELIANCE"

            # Legacy path still works
            q2 = broker.market.quote("RELIANCE")
            assert q2.ltp > 0

            # Canonical quote method works
            q3 = broker.market.quote("RELIANCE")
            assert isinstance(q3, Quote)
        finally:
            broker.close()

    def test_legacy_operations_still_work(self) -> None:
        """Verify old broker.orders.place_order() still works."""
        from inc_trade.domain.enums import Side

        import brokers

        broker = brokers.connect("paper")
        try:
            resp = broker.orders.place_order("RELIANCE", "NSE", Side.BUY, 10)
            assert resp.success is True
            assert resp.order_id.startswith("PAPER-")

            orders = broker.orders.get_orders()
            assert len(orders) >= 1
        finally:
            broker.close()

    def test_legacy_portfolio_still_works(self) -> None:
        """Verify old broker.portfolio.get_balance() still works."""
        from inc_trade.domain import Balance

        import brokers

        broker = brokers.connect("paper")
        try:
            # BrokerFacade (returned in facade-delegation mode) uses get_balance()
            balance = broker.portfolio.get_balance()
            assert isinstance(balance, Balance)
            assert balance.available_cash > 0
        finally:
            broker.close()

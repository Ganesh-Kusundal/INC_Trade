"""End-to-end smoke tests for every Dhan feature exercised in the manual
``scripts/test_dhan_all_modes.py`` — now as a first-class pytest suite.

Running the script after this file exists is just a thin wrapper:

    python scripts/test_dhan_all_modes.py
    # internally calls:
    # pytest brokers/dhan/tests/regression/test_e2e_smoke.py -v

This file is split into two groups:

  ``TestOffMarketSmoke``  — REST-only, safe outside market hours.
  ``TestMarketHoursSmoke``— WebSocket/streaming, requires NSE open
                            (or FORCE_MARKET_OPEN=1).

All tests use the session-scoped ``live_gateway`` fixture provided by the
integration conftest; they are auto-tagged ``dhan``, ``integration``,
``sandbox`` by that conftest.
"""

from __future__ import annotations

import contextlib
import threading
import time

import pytest

from tests.market_hours import require_market_hours

pytestmark = [pytest.mark.dhan, pytest.mark.regression]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NSE_EQUITY = [("RELIANCE", "NSE"), ("TCS", "NSE"), ("INFOSYS", "NSE")]
INDEX = [("NIFTY", "INDEX"), ("BANKNIFTY", "INDEX")]
NFO_INDEX = [("NIFTY", "NFO"), ("BANKNIFTY", "NFO")]


# ---------------------------------------------------------------------------
# Off-market smoke (REST)
# ---------------------------------------------------------------------------

@pytest.mark.off_market_safe
class TestOffMarketSmoke:
    """REST-based smoke; safe to run anytime with live creds."""

    @pytest.mark.parametrize("symbol,exchange", NSE_EQUITY, ids=lambda x: x if isinstance(x, str) else "")
    def test_ltp(self, live_gateway, symbol, exchange):
        """LTP must be a positive Decimal."""
        from decimal import Decimal
        ltp = live_gateway.ltp(symbol, exchange)
        assert isinstance(ltp, Decimal), f"{symbol} LTP type wrong: {type(ltp)}"
        assert ltp > 0, f"{symbol} LTP not positive: {ltp}"
        time.sleep(1.0)

    @pytest.mark.parametrize("symbol,exchange", NSE_EQUITY, ids=lambda x: x if isinstance(x, str) else "")
    def test_quote(self, live_gateway, symbol, exchange):
        """Quote must have valid OHLCV and LTP > 0."""
        q = live_gateway.quote(symbol, exchange)
        assert q.ltp > 0, f"{symbol} quote LTP invalid: {q.ltp}"
        assert q.high >= q.low, f"{symbol} high < low"
        assert q.open >= 0
        time.sleep(1.0)

    @pytest.mark.parametrize("symbol,exchange", NSE_EQUITY[:1])  # limit to avoid rate limit
    def test_rest_depth(self, live_gateway, symbol, exchange):
        """REST depth must have at least 1 bid and 1 ask."""
        depth = live_gateway.depth(symbol, exchange)
        assert len(depth.bids) >= 1, f"{symbol} REST depth bids empty"
        assert len(depth.asks) >= 1, f"{symbol} REST depth asks empty"
        assert depth.bids[0].price > 0
        assert depth.asks[0].price > 0

    @pytest.mark.parametrize("symbol,exchange", INDEX, ids=lambda x: x if isinstance(x, str) else "")
    def test_index_ltp(self, live_gateway, symbol, exchange):
        """Index LTP must be positive."""
        from decimal import Decimal
        ltp = live_gateway.ltp(symbol, exchange)
        assert isinstance(ltp, Decimal) and ltp > 0
        time.sleep(1.0)

    @pytest.mark.parametrize("underlying,exchange", NFO_INDEX, ids=lambda x: x if isinstance(x, str) else "")
    def test_option_chain(self, live_gateway, underlying, exchange):
        """Option chain must have strikes and valid spot."""
        chain = live_gateway.option_chain(underlying, exchange)
        assert chain.spot > 0, f"{underlying} option chain spot invalid"
        assert len(chain.strikes) > 0, f"{underlying} option chain empty"
        expiries = live_gateway.extended.get_option_expiries(
            underlying, "INDEX" if underlying in ("NIFTY", "BANKNIFTY", "FINNIFTY") else "NSE"
        )
        assert len(expiries) >= 1, f"{underlying} extended expiries empty"
        time.sleep(1.5)

    @pytest.mark.parametrize("underlying,exchange", [*NFO_INDEX, ("RELIANCE", "NFO")],
                              ids=lambda x: x if isinstance(x, str) else "")
    def test_future_chain(self, live_gateway, underlying, exchange):
        """Futures chain must have at least 1 contract with expiry."""
        chain = live_gateway.future_chain(underlying, exchange)
        assert len(chain.contracts) >= 1, f"{underlying} futures empty"
        assert chain.contracts[0].expiry is not None
        time.sleep(0.5)

    def test_portfolio_funds(self, live_gateway):
        """funds() must return a Balance object."""
        bal = live_gateway.funds()
        assert bal is not None
        assert hasattr(bal, "available_balance")

    def test_portfolio_positions(self, live_gateway):
        """positions() must return a list."""
        assert isinstance(live_gateway.positions(), list)

    def test_portfolio_holdings(self, live_gateway):
        """holdings() must return a list."""
        assert isinstance(live_gateway.holdings(), list)

    def test_batch_ltp(self, live_gateway):
        """ltp_batch() must return non-empty dict."""
        results = live_gateway.ltp_batch(["RELIANCE", "TCS"], "NSE")
        assert isinstance(results, dict)
        assert len(results) >= 1

    def test_history_daily(self, live_gateway):
        """history() 1D must return DataFrame with OHLCV."""
        df = live_gateway.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)
        assert df is not None and len(df) > 0
        for col in ("open", "high", "low", "close", "volume"):
            assert col in df.columns

    def test_reliance_stock_option_chain(self, live_gateway):
        """RELIANCE OPTSTK chain must have strikes (underlying exchange = NSE)."""
        chain = live_gateway.option_chain("RELIANCE", "NSE")
        assert chain.spot > 0
        assert len(chain.strikes) > 0

    def test_reliance_stock_futures(self, live_gateway):
        """RELIANCE FUTSTK must have contracts (underlying exchange = NSE)."""
        chain = live_gateway.future_chain("RELIANCE", "NSE")
        assert len(chain.contracts) >= 1
        time.sleep(1.0)


# ---------------------------------------------------------------------------
# Market-hours smoke (WebSocket / streaming)
# ---------------------------------------------------------------------------

@pytest.mark.market_hours
@require_market_hours()
class TestMarketHoursSmoke:
    """WebSocket smoke — requires NSE market hours (or FORCE_MARKET_OPEN=1)."""

    def test_depth_20_initial_has_both_sides(self, live_gateway):
        """depth_20() initial return must include both bids and asks (REST merge fix)."""
        depth = live_gateway.depth_20("RELIANCE", "NSE")
        assert len(depth.bids) >= 1, "depth_20() bids empty"
        assert len(depth.asks) >= 1, "depth_20() asks empty — REST merge broken"
        time.sleep(1.0)

    def test_ltp_stream(self, live_gateway):
        """LTP stream must receive ticks within 15 s."""
        received = threading.Event()
        ticks: list[object] = []

        def on_tick(q):
            ticks.append(q)
            received.set()

        feed = live_gateway.stream("RELIANCE", "NSE", mode="LTP", on_tick=on_tick)
        try:
            got = received.wait(timeout=15)
            assert got and len(ticks) > 0, "LTP stream: 0 ticks in 15 s"
        finally:
            with contextlib.suppress(Exception):
                feed.disconnect()

    def test_quote_stream(self, live_gateway):
        """QUOTE stream must receive ticks within 15 s."""
        received = threading.Event()
        ticks: list[object] = []

        def on_tick(q):
            ticks.append(q)
            received.set()

        feed = live_gateway.stream("TCS", "NSE", mode="QUOTE", on_tick=on_tick)
        try:
            got = received.wait(timeout=15)
            assert got and len(ticks) > 0, "QUOTE stream: 0 ticks in 15 s"
        finally:
            with contextlib.suppress(Exception):
                feed.disconnect()
            time.sleep(1)

    def test_full_mode_stream(self, live_gateway):
        """FULL mode must receive ticks within 15 s."""
        received = threading.Event()
        ticks: list[object] = []

        def on_tick(q):
            ticks.append(q)
            received.set()

        feed = live_gateway.stream("INFOSYS", "NSE", mode="FULL", on_tick=on_tick)
        try:
            got = received.wait(timeout=15)
            assert got and len(ticks) > 0, "FULL mode: 0 ticks in 15 s"
        finally:
            with contextlib.suppress(Exception):
                feed.disconnect()

    def test_depth_20_ws_updates(self, live_gateway):
        """depth_20() EventBus must receive at least one depth update in 10 s."""
        received = threading.Event()
        updates: list[object] = []

        def on_depth(event):
            updates.append(event)
            received.set()

        # Subscribe via EventBus before starting the feed
        bus = live_gateway._conn.event_bus if hasattr(live_gateway._conn, "event_bus") else None
        if bus is None:
            pytest.skip("live_gateway has no event_bus")

        unsub = bus.subscribe("DEPTH_20", on_depth)
        try:
            # Trigger depth_20 feed startup
            live_gateway.depth_20("RELIANCE", "NSE")
            got = received.wait(timeout=10)
            assert got and len(updates) > 0, "Depth-20 WS: 0 EventBus events in 10 s"
        finally:
            with contextlib.suppress(Exception):
                unsub()

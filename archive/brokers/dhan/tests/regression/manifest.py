"""Dhan regression suite manifest.

Single source of truth mapping every P0/P1 Dhan capability to:
  - the tier it belongs to (off_market_safe | market_hours | pre_prod | sandbox)
  - the exchange segment under test
  - a short assertion function called by the parametrized orchestrator in
    ``test_regression_suite.py``

Adding a new capability?  Add an entry here; ``test_coverage_manifest.py``
will fail CI if any P0 capability has no registered case.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field

from brokers.dhan.gateway import BrokerGateway

Tier = str  # "off_market_safe" | "market_hours" | "pre_prod" | "sandbox"


@dataclass(frozen=True)
class RegressionCase:
    """One regression assertion for a Dhan capability."""

    id: str
    capability: str
    tier: Tier
    segment: str
    description: str
    assert_fn: Callable[[BrokerGateway], None]
    severity: str = "P0"  # P0 | P1 | P2
    tags: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Assertion helpers — each is a self-contained function executed against the
# live gateway during a regression run.
# ---------------------------------------------------------------------------

def _assert_nse_ltp(gw: BrokerGateway) -> None:
    from decimal import Decimal
    ltp = gw.ltp("RELIANCE", "NSE")
    assert isinstance(ltp, Decimal) and ltp > 0, f"NSE LTP invalid: {ltp}"


def _assert_nse_quote(gw: BrokerGateway) -> None:
    q = gw.quote("RELIANCE", "NSE")
    assert q.ltp > 0, f"NSE quote LTP invalid: {q.ltp}"
    assert q.open >= 0
    assert q.high >= q.low


def _assert_nse_depth(gw: BrokerGateway) -> None:
    depth = gw.depth("RELIANCE", "NSE")
    assert len(depth.bids) >= 1, "NSE REST depth: no bids"
    assert len(depth.asks) >= 1, "NSE REST depth: no asks"
    assert depth.bids[0].price > 0
    assert depth.asks[0].price > 0


def _assert_nse_history(gw: BrokerGateway) -> None:
    df = gw.history("RELIANCE", "NSE", timeframe="1D", lookback_days=5)
    assert df is not None and len(df) > 0, "NSE history returned empty"
    for col in ("open", "high", "low", "close", "volume"):
        assert col in df.columns, f"Missing column: {col}"


def _assert_index_ltp(gw: BrokerGateway) -> None:
    from decimal import Decimal
    ltp = gw.ltp("NIFTY", "INDEX")
    assert isinstance(ltp, Decimal) and ltp > 0, f"INDEX LTP invalid: {ltp}"


def _assert_nfo_option_chain(gw: BrokerGateway) -> None:
    chain = gw.option_chain("NIFTY", "NFO")
    assert chain.spot > 0, f"NIFTY option chain spot invalid: {chain.spot}"
    assert len(chain.strikes) > 0, "NIFTY option chain has no strikes"


def _assert_nfo_option_chain_banknifty(gw: BrokerGateway) -> None:
    chain = gw.option_chain("BANKNIFTY", "NFO")
    assert chain.spot > 0
    assert len(chain.strikes) > 0


def _assert_nfo_future_chain_nifty(gw: BrokerGateway) -> None:
    fc = gw.future_chain("NIFTY", "NFO")
    assert len(fc.contracts) >= 1, "NIFTY future chain empty"
    assert fc.contracts[0].expiry is not None


def _assert_nfo_future_chain_reliance(gw: BrokerGateway) -> None:
    # For stock futures the underlying exchange is NSE (not NFO)
    fc = gw.future_chain("RELIANCE", "NSE")
    assert len(fc.contracts) >= 1, "RELIANCE future chain empty"


def _assert_portfolio_funds(gw: BrokerGateway) -> None:
    bal = gw.funds()
    assert bal is not None, "funds() returned None"
    # available_balance may be 0 in a fresh account; must not raise
    assert hasattr(bal, "available_balance")


def _assert_portfolio_positions(gw: BrokerGateway) -> None:
    positions = gw.positions()
    assert isinstance(positions, list), "positions() must return a list"


def _assert_portfolio_holdings(gw: BrokerGateway) -> None:
    holdings = gw.holdings()
    assert isinstance(holdings, list), "holdings() must return a list"


def _assert_batch_ltp(gw: BrokerGateway) -> None:
    results = gw.ltp_batch(["RELIANCE", "TCS"], "NSE")
    assert isinstance(results, dict)
    assert len(results) >= 1, "batch LTP returned empty"


def _assert_nse_instruments_search(gw: BrokerGateway) -> None:
    results = gw.search_instruments("RELIANCE")
    assert isinstance(results, list) and len(results) >= 1


def _assert_observability_cb(gw: BrokerGateway) -> None:
    health = gw.health()
    assert health is not None, "health() returned None"


def _assert_subscription_engine_wired(gw: BrokerGateway) -> None:
    """P0: gateway must delegate streaming to SubscriptionEngine."""
    conn = gw._conn
    assert hasattr(conn, "subscription_engine"), "missing SubscriptionEngine on connection"
    engine = conn.subscription_engine
    assert callable(getattr(engine, "subscribe_market", None))
    assert callable(getattr(engine, "unsubscribe_market", None))


def _assert_session_manager_wired(gw: BrokerGateway) -> None:
    """P0: connection must expose consolidated session manager."""
    conn = gw._conn
    assert hasattr(conn, "_session_manager"), "missing DhanSessionManager on connection"
    sm = conn._session_manager
    assert callable(getattr(sm, "health_summary", None))


def _assert_stream_order_not_market_alias(gw: BrokerGateway) -> None:
    """P0: gateway must expose distinct order stream entry point."""
    assert callable(getattr(gw, "stream_order", None))
    assert callable(getattr(gw, "unstream_order", None))
    assert gw.stream_order is not gw.stream


def _assert_nse_depth_both_sides(gw: BrokerGateway) -> None:
    """After the fix: REST depth always returns both sides."""
    depth = gw.depth("TCS", "NSE")
    assert len(depth.bids) >= 1, "depth() bids empty after fix"
    assert len(depth.asks) >= 1, "depth() asks empty after fix"


def _assert_nfo_stock_option_chain(gw: BrokerGateway) -> None:
    """Stock options (OPTSTK): RELIANCE option chain (underlying exchange = NSE)."""
    chain = gw.option_chain("RELIANCE", "NSE")
    assert chain.spot > 0
    assert len(chain.strikes) > 0, "Stock option chain (RELIANCE) has no strikes"


def _assert_nfo_banknifty_future(gw: BrokerGateway) -> None:
    """BANKNIFTY futures via NFO."""
    fc = gw.future_chain("BANKNIFTY", "NFO")
    assert len(fc.contracts) >= 1, "BANKNIFTY future chain empty"


# Market-hours cases — WebSocket / streaming (skipped off-market)

def _assert_depth_20_both_sides(gw: BrokerGateway) -> None:
    """depth_20() initial return has both bids and asks (merged with REST)."""
    import time
    depth = gw.depth_20("RELIANCE", "NSE")
    # After the depth-merge fix the initial call must always have both sides
    assert len(depth.bids) >= 1, "depth_20() bids empty"
    assert len(depth.asks) >= 1, "depth_20() asks empty (REST merge broken)"
    time.sleep(1.0)


def _assert_full_mode_tick(gw: BrokerGateway) -> None:
    """FULL mode stream receives at least one tick within 15 s during market hours."""
    import threading
    received = threading.Event()
    ticks: list[object] = []

    def on_tick(q):
        ticks.append(q)
        received.set()

    feed = gw.stream("RELIANCE", "NSE", mode="FULL", on_tick=on_tick)
    try:
        got = received.wait(timeout=15)
        assert got and len(ticks) > 0, "FULL mode: 0 ticks received in 15 s during market hours"
    finally:
        with contextlib.suppress(Exception):
            feed.disconnect()


# ---------------------------------------------------------------------------
# Manifest — canonical list of regression cases
# ---------------------------------------------------------------------------

OFF_MARKET_CASES: list[RegressionCase] = [
    RegressionCase(
        id="nse_ltp",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="NSE equity LTP > 0",
        assert_fn=_assert_nse_ltp,
        severity="P0",
    ),
    RegressionCase(
        id="nse_quote",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="NSE equity quote has valid OHLCV",
        assert_fn=_assert_nse_quote,
        severity="P0",
    ),
    RegressionCase(
        id="nse_depth_rest",
        capability="supports_depth",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="NSE REST depth has bids and asks",
        assert_fn=_assert_nse_depth,
        severity="P0",
    ),
    RegressionCase(
        id="nse_depth_both_sides_fix",
        capability="supports_depth",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="REST depth always returns both sides (regression fix)",
        assert_fn=_assert_nse_depth_both_sides,
        severity="P0",
        tags=("regression_fix",),
    ),
    RegressionCase(
        id="nse_history_daily",
        capability="supports_historical_data",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="NSE daily history returns OHLCV DataFrame",
        assert_fn=_assert_nse_history,
        severity="P0",
    ),
    RegressionCase(
        id="index_ltp",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="IDX_I",
        description="NIFTY INDEX LTP > 0",
        assert_fn=_assert_index_ltp,
        severity="P0",
    ),
    RegressionCase(
        id="nfo_option_chain_nifty",
        capability="supports_option_chain",
        tier="off_market_safe",
        segment="NFO",
        description="NIFTY option chain has strikes and spot",
        assert_fn=_assert_nfo_option_chain,
        severity="P0",
    ),
    RegressionCase(
        id="nfo_option_chain_banknifty",
        capability="supports_option_chain",
        tier="off_market_safe",
        segment="NFO",
        description="BANKNIFTY option chain has strikes and spot",
        assert_fn=_assert_nfo_option_chain_banknifty,
        severity="P0",
    ),
    RegressionCase(
        id="nfo_future_chain_nifty",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NFO",
        description="NIFTY futures chain has at least 1 contract",
        assert_fn=_assert_nfo_future_chain_nifty,
        severity="P0",
    ),
    RegressionCase(
        id="nfo_future_chain_reliance",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NFO",
        description="RELIANCE stock futures chain has at least 1 contract",
        assert_fn=_assert_nfo_future_chain_reliance,
        severity="P1",
    ),
    RegressionCase(
        id="nfo_stock_option_chain_reliance",
        capability="supports_option_chain",
        tier="off_market_safe",
        segment="NFO",
        description="RELIANCE stock options (OPTSTK) chain has strikes",
        assert_fn=_assert_nfo_stock_option_chain,
        severity="P1",
    ),
    RegressionCase(
        id="nfo_future_chain_banknifty",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NFO",
        description="BANKNIFTY future chain has at least 1 contract",
        assert_fn=_assert_nfo_banknifty_future,
        severity="P1",
    ),
    RegressionCase(
        id="portfolio_funds",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="funds() returns Balance object",
        assert_fn=_assert_portfolio_funds,
        severity="P0",
    ),
    RegressionCase(
        id="portfolio_positions",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="positions() returns list",
        assert_fn=_assert_portfolio_positions,
        severity="P0",
    ),
    RegressionCase(
        id="portfolio_holdings",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="holdings() returns list",
        assert_fn=_assert_portfolio_holdings,
        severity="P0",
    ),
    RegressionCase(
        id="batch_ltp",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="ltp_batch() returns dict with results",
        assert_fn=_assert_batch_ltp,
        severity="P1",
    ),
    RegressionCase(
        id="instruments_search",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="search_instruments() returns results",
        assert_fn=_assert_nse_instruments_search,
        severity="P1",
    ),
    RegressionCase(
        id="observability_health",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="health() returns status",
        assert_fn=_assert_observability_cb,
        severity="P1",
    ),
    RegressionCase(
        id="arch_subscription_engine",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="SubscriptionEngine is wired on the live connection",
        assert_fn=_assert_subscription_engine_wired,
        severity="P0",
        tags=("architecture",),
    ),
    RegressionCase(
        id="arch_session_manager",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="DhanSessionManager is wired on the live connection",
        assert_fn=_assert_session_manager_wired,
        severity="P0",
        tags=("architecture",),
    ),
    RegressionCase(
        id="arch_stream_order_entry",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="Order stream entry point is distinct from market stream",
        assert_fn=_assert_stream_order_not_market_alias,
        severity="P0",
        tags=("architecture",),
    ),
]

MARKET_HOURS_CASES: list[RegressionCase] = [
    RegressionCase(
        id="depth_20_both_sides",
        capability="supports_depth_20_ws",
        tier="market_hours",
        segment="NSE_EQ",
        description="depth_20() initial return has bids and asks (REST merge fix)",
        assert_fn=_assert_depth_20_both_sides,
        severity="P0",
        tags=("regression_fix",),
    ),
    RegressionCase(
        id="full_mode_tick",
        capability="supports_live_market_data",
        tier="market_hours",
        segment="NSE_EQ",
        description="FULL mode stream receives ticks during market hours",
        assert_fn=_assert_full_mode_tick,
        severity="P0",
    ),
]

# All P0 capability names that must have at least one registered case
P0_CAPABILITIES: frozenset[str] = frozenset(
    c.capability for c in OFF_MARKET_CASES + MARKET_HOURS_CASES if c.severity == "P0"
)

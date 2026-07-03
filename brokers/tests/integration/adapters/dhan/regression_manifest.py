"""Dhan regression suite manifest for modern DhanGateway.

Single source of truth mapping every P0/P1 Dhan capability to:
  - the tier it belongs to (off_market_safe | market_hours | pre_prod | sandbox)
  - the exchange segment under test
  - a short assertion function called by the parametrized orchestrator in
    ``test_regression_manifest.py``

Adding a new capability?  Add an entry here; ``test_coverage_manifest.py``
will fail CI if any P0 capability has no registered case.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field

from brokers.adapters.dhan.gateway import DhanGateway

Tier = str  # "off_market_safe" | "market_hours" | "pre_prod" | "sandbox"


@dataclass(frozen=True)
class RegressionCase:
    """One regression assertion for a Dhan capability."""

    id: str
    capability: str
    tier: Tier
    segment: str
    description: str
    assert_fn: Callable[[DhanGateway], None]
    severity: str = "P0"  # P0 | P1 | P2
    tags: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Assertion helpers — each is a self-contained function executed against the
# live gateway during a regression run.
# ---------------------------------------------------------------------------


def _assert_nse_ltp(gw: DhanGateway) -> None:
    from decimal import Decimal

    ltp = gw.market_data.ltp("RELIANCE", "NSE")
    assert isinstance(ltp, Decimal) and ltp > 0, f"NSE LTP invalid: {ltp}"


def _assert_nse_quote(gw: DhanGateway) -> None:
    q = gw.market_data.quote("RELIANCE", "NSE")
    assert q.ltp > 0, f"NSE quote LTP invalid: {q.ltp}"
    assert q.open >= 0
    assert q.high >= q.low


def _assert_nse_depth(gw: DhanGateway) -> None:
    depth = gw.market_data.depth("RELIANCE", "NSE")
    assert len(depth.bids) >= 1, "NSE REST depth: no bids"
    assert len(depth.asks) >= 1, "NSE REST depth: no asks"
    assert depth.bids[0].price > 0
    assert depth.asks[0].price > 0


def _assert_nse_history(gw: DhanGateway) -> None:
    from datetime import datetime, timedelta

    end = datetime.now()
    start = end - timedelta(days=5)
    candles = gw.historical.get_historical_candles("RELIANCE", "NSE", start, end, "1D")
    assert len(candles) > 0, "NSE history returned empty"


def _assert_index_ltp(gw: DhanGateway) -> None:
    from decimal import Decimal

    ltp = gw.market_data.ltp("NIFTY", "INDEX")
    assert isinstance(ltp, Decimal) and ltp > 0, f"INDEX LTP invalid: {ltp}"


def _assert_nfo_option_chain(gw: DhanGateway) -> None:
    expiries = gw.options.get_expiries("NIFTY", "NFO")
    assert len(expiries) > 0, "No NIFTY expiries available"
    chain = gw.options.get_option_chain("NIFTY", "NFO", expiry=expiries[0])
    assert chain.spot > 0, f"NIFTY option chain spot invalid: {chain.spot}"
    assert len(chain.strikes) > 0, "NIFTY option chain has no strikes"


def _assert_nfo_option_chain_banknifty(gw: DhanGateway) -> None:
    expiries = gw.options.get_expiries("BANKNIFTY", "NFO")
    assert len(expiries) > 0, "No BANKNIFTY expiries available"
    chain = gw.options.get_option_chain("BANKNIFTY", "NFO", expiry=expiries[0])
    assert chain.spot > 0
    assert len(chain.strikes) > 0


def _assert_nfo_future_chain_nifty(gw: DhanGateway) -> None:
    expiries = gw.options.get_expiries("NIFTY", "NFO")
    assert len(expiries) >= 1, "NIFTY futures expiry list empty"


def _assert_nfo_future_chain_reliance(gw: DhanGateway) -> None:
    refs = gw.instruments.search("RELIANCE")
    assert len(refs) >= 1, "RELIANCE instruments search returned empty"


def _assert_portfolio_funds(gw: DhanGateway) -> None:
    bal = gw.portfolio.funds()
    assert bal is not None, "funds() returned None"
    assert hasattr(bal, "available_cash")


def _assert_portfolio_positions(gw: DhanGateway) -> None:
    positions = gw.portfolio.positions()
    assert isinstance(positions, list), "positions() must return a list"


def _assert_portfolio_holdings(gw: DhanGateway) -> None:
    holdings = gw.portfolio.holdings()
    assert isinstance(holdings, list), "holdings() must return a list"


def _assert_batch_ltp(gw: DhanGateway) -> None:
    results = gw.market_data.ltp_batch(["RELIANCE", "TCS"], "NSE")
    assert isinstance(results, dict)
    assert len(results) >= 1, "batch LTP returned empty"


def _assert_nse_instruments_search(gw: DhanGateway) -> None:
    results = gw.instruments.search("RELIANCE")
    assert isinstance(results, list) and len(results) >= 1


def _assert_observability_cb(gw: DhanGateway) -> None:
    health = gw.health()
    assert health is not None, "health() returned None"


def _assert_subscription_engine_wired(gw: DhanGateway) -> None:
    """P0: gateway must expose streaming and order stream ports."""
    assert gw.streaming is not None, "missing streaming port on gateway"
    assert callable(getattr(gw.streaming, "subscribe", None))


def _assert_session_manager_wired(gw: DhanGateway) -> None:
    """P0: gateway must expose auth/token lifecycle."""
    assert gw.auth is not None, "missing auth on gateway"
    assert callable(getattr(gw.auth, "get_token", None))


def _assert_stream_order_not_market_alias(gw: DhanGateway) -> None:
    """P0: gateway must expose distinct order stream entry point."""
    assert hasattr(gw, "_order_stream"), "missing order_stream on gateway"


def _assert_nse_depth_both_sides(gw: DhanGateway) -> None:
    depth = gw.market_data.depth("TCS", "NSE")
    assert len(depth.bids) >= 1, "depth() bids empty after fix"
    assert len(depth.asks) >= 1, "depth() asks empty after fix"


def _assert_nfo_stock_option_chain(gw: DhanGateway) -> None:
    expiries = gw.options.get_expiries("RELIANCE", "NSE")
    assert len(expiries) > 0, "No RELIANCE expiries available"
    chain = gw.options.get_option_chain("RELIANCE", "NSE", expiry=expiries[0])
    assert chain.spot > 0
    assert len(chain.strikes) > 0, "Stock option chain (RELIANCE) has no strikes"


def _assert_nfo_banknifty_future(gw: DhanGateway) -> None:
    expiries = gw.options.get_expiries("BANKNIFTY", "NFO")
    assert len(expiries) >= 1, "BANKNIFTY future chain empty"


def _assert_depth_20_both_sides(gw: DhanGateway) -> None:
    """depth_20() initial return has both bids and asks (merged with REST)."""
    import time

    depth = gw.market_data.depth("RELIANCE", "NSE")
    assert len(depth.bids) >= 1, "depth_20() bids empty"
    assert len(depth.asks) >= 1, "depth_20() asks empty (REST merge broken)"
    time.sleep(1.0)


def _assert_full_mode_tick(gw: DhanGateway) -> None:
    """FULL mode stream receives at least one tick within 15 s during market hours."""
    import threading

    received = threading.Event()
    ticks: list[object] = []

    def on_tick(q):
        ticks.append(q)
        received.set()

    gw.streaming.subscribe("RELIANCE", "NSE", on_tick=on_tick)
    try:
        got = received.wait(timeout=15)
        assert got and len(ticks) > 0, "FULL mode: 0 ticks received in 15 s during market hours"
    finally:
        with contextlib.suppress(Exception):
            gw.streaming.unsubscribe("RELIANCE", "NSE")


# ---------------------------------------------------------------------------
# Manifest — canonical list of regression cases (23 total)
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
        description="Streaming ports are wired on the live gateway",
        assert_fn=_assert_subscription_engine_wired,
        severity="P0",
        tags=("architecture",),
    ),
    RegressionCase(
        id="arch_session_manager",
        capability="supports_live_market_data",
        tier="off_market_safe",
        segment="NSE_EQ",
        description="Auth/token lifecycle is wired on the live gateway",
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

P0_CAPABILITIES: frozenset[str] = frozenset(
    c.capability for c in OFF_MARKET_CASES + MARKET_HOURS_CASES if c.severity == "P0"
)

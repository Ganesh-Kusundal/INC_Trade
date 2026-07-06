"""Unit tests for the enhanced Instrument methods (oi, metadata, greeks, market_status)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock

import pytest
from inc_trade.market.instrument import Instrument
from inc_trade.market.quote_state import QuoteState


@pytest.fixture
def context() -> Any:
    ctx = MagicMock()
    state = QuoteState(
        composite_key="NSE:RELIANCE",
        ltp=Decimal("2500"),
        open=Decimal("2480"),
        high=Decimal("2520"),
        low=Decimal("2475"),
        close=Decimal("2490"),
        volume=100000,
        oi=50000,
        timestamp=datetime.now(UTC),
    )
    ctx.quote_state.return_value = state
    ctx.quote.return_value = MagicMock(ltp=Decimal("2500"))
    return ctx


def _attach(inst: Instrument, ctx: Any) -> Instrument:
    """Attach a market data context to a frozen Instrument."""
    object.__setattr__(inst, "_context", ctx)
    return inst


class TestInstrumentOI:
    def test_oi_returns_from_state(self, context: Any) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        _attach(inst, context)
        assert inst.oi() == 50000

    def test_oi_returns_zero_without_context(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        assert inst.oi() == 0


class TestInstrumentMetadata:
    def test_metadata_includes_all_fields(self) -> None:
        inst = Instrument(
            symbol="RELIANCE",
            exchange="NSE",
            segment="NSE_EQ",
            name="Reliance Industries",
            lot_size=1,
            tick_size=Decimal("0.05"),
            isin="INE002A01018",
        )
        meta = inst.metadata()
        assert meta["symbol"] == "RELIANCE"
        assert meta["exchange"] == "NSE"
        assert meta["name"] == "Reliance Industries"
        assert meta["lot_size"] == 1
        assert meta["tick_size"] == Decimal("0.05")
        assert meta["isin"] == "INE002A01018"

    def test_metadata_for_option(self) -> None:
        inst = Instrument(
            symbol="NIFTY",
            exchange="NFO",
            segment="NSE_FNO",
            strike=Decimal("18000"),
            option_type="CE",
            expiry=datetime(2025, 1, 30, tzinfo=UTC),
        )
        meta = inst.metadata()
        assert meta["strike"] == Decimal("18000")
        assert meta["option_type"] == "CE"
        assert meta["expiry"] is not None


class TestInstrumentMarketStatus:
    def test_open_with_recent_state(self, context: Any) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        _attach(inst, context)
        assert inst.market_status() == "open"

    def test_closed_when_stale(self) -> None:
        ctx = MagicMock()
        state = QuoteState(
            composite_key="NSE:RELIANCE",
            timestamp=datetime(2020, 1, 1, tzinfo=UTC),
        )
        ctx.quote_state.return_value = state
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        _attach(inst, ctx)
        assert inst.market_status() == "closed"

    def test_unknown_when_no_context(self) -> None:
        inst = Instrument(symbol="X", exchange="NSE")
        assert inst.market_status() == "unknown"

    def test_unknown_when_quote_state_fails(self) -> None:
        ctx = MagicMock()
        ctx.quote_state.side_effect = Exception("no data")
        inst = Instrument(symbol="X", exchange="NSE")
        _attach(inst, ctx)
        assert inst.market_status() == "unknown"


class TestInstrumentGreeks:
    def test_empty_for_non_option(self, context: Any) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        _attach(inst, context)
        assert inst.greeks() == {}

    def test_returns_dict_for_option(self, context: Any) -> None:
        inst = Instrument(
            symbol="NIFTY",
            exchange="NFO",
            strike=Decimal("18000"),
            option_type="CE",
        )
        _attach(inst, context)
        greeks = inst.greeks()
        assert greeks["ltp"] == Decimal("2500")
        assert greeks["oi"] == 50000
        assert greeks["volume"] == 100000
        # IV/Delta/Theta/Gamma/Vega not in QuoteState by default
        assert greeks["iv"] is None


class TestInstrumentUnchangedBehavior:
    """Sanity: existing methods still work after the addition."""

    def test_quote_delegates(self, context: Any) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        _attach(inst, context)
        inst.quote()
        context.quote.assert_called_once()

    def test_ltp_delegates(self, context: Any) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        _attach(inst, context)
        inst.ltp()
        context.ltp.assert_called_once()

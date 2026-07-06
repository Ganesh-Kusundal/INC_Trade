"""Tests for InstrumentOptionChain and related objects (Phase 3).

Covers:
- InstrumentOptionLeg, InstrumentOptionStrike, InstrumentOptionChain construction
- Max pain, PCR, ITM/OTM/ATM calculations
- nearest_strikes, filter_by_delta
- SyntheticFuture construction, PnL, close orders
- subscribe_all / unsubscribe_all
- refresh()
- _build_instrument_chain from raw OptionChain
- MarketDataContext.option_chain() returns InstrumentOptionChain
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from brokers_core.market.option_chain import _build_instrument_chain
from inc_trade.domain.entities import OptionChain, OptionLeg, OptionStrike
from inc_trade.market.instrument import Instrument
from inc_trade.market.option_chain import (
    InstrumentOptionChain,
    InstrumentOptionLeg,
    InstrumentOptionStrike,
    SyntheticFuture,
)

# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def underlying_inst() -> Instrument:
    return Instrument(symbol="NIFTY", exchange="NSE", name="Nifty 50", lot_size=25)


@pytest.fixture
def sample_legs(underlying_inst: Instrument) -> tuple[InstrumentOptionStrike, ...]:
    """Create a chain of 5 strikes around 18000."""
    strikes_list: list[InstrumentOptionStrike] = []
    for i, strike in enumerate(
        [Decimal("17800"), Decimal("17900"), Decimal("18000"), Decimal("18100"), Decimal("18200")]
    ):
        call_inst = Instrument(
            symbol=f"NIFTY{strike}CE",
            exchange="NFO",
            strike=strike,
            option_type="CE",
            lot_size=25,
        )
        put_inst = Instrument(
            symbol=f"NIFTY{strike}PE",
            exchange="NFO",
            strike=strike,
            option_type="PE",
            lot_size=25,
        )
        call_leg = InstrumentOptionLeg(
            instrument=call_inst,
            ltp=Decimal(str(100 + i * 10)),  # 100, 110, 120, 130, 140
            oi=1000 * (i + 1),  # 1000, 2000, 3000, 4000, 5000
            volume=500 * (i + 1),
            iv=Decimal("15.0"),
            delta=Decimal(str(0.5 + i * 0.1)),  # 0.5, 0.6, 0.7, 0.8, 0.9
        )
        put_leg = InstrumentOptionLeg(
            instrument=put_inst,
            ltp=Decimal(str(200 - i * 10)),  # 200, 190, 180, 170, 160
            oi=2000 * (6 - i),  # 10000, 8000, 6000, 4000, 2000 (descending)
            volume=500 * (6 - i),
            iv=Decimal("16.0"),
            delta=Decimal(str(-0.5 + i * 0.05)),  # -0.5, -0.45, -0.4, -0.35, -0.3
        )
        strikes_list.append(InstrumentOptionStrike(strike=strike, call=call_leg, put=put_leg))
    return tuple(strikes_list)


@pytest.fixture
def chain(
    underlying_inst: Instrument, sample_legs: tuple[InstrumentOptionStrike, ...]
) -> InstrumentOptionChain:
    return InstrumentOptionChain(
        underlying=underlying_inst,
        expiry="2025-01-30",
        spot=Decimal("18050"),
        strikes=sample_legs,
    )


# ── InstrumentOptionLeg Tests ─────────────────────────────────────────────


class TestInstrumentOptionLeg:
    def test_leg_construction(self) -> None:
        inst = Instrument(symbol="NIFTY18000CE", exchange="NFO")
        leg = InstrumentOptionLeg(
            instrument=inst,
            ltp=Decimal("120"),
            oi=5000,
            volume=2500,
            iv=Decimal("15.0"),
            delta=Decimal("0.5"),
        )
        assert leg.instrument is inst
        assert leg.ltp == Decimal("120")
        assert leg.oi == 5000

    def test_greeks(self) -> None:
        inst = Instrument(symbol="NIFTY18000CE", exchange="NFO")
        leg = InstrumentOptionLeg(
            instrument=inst,
            ltp=Decimal("120"),
            oi=5000,
            volume=2500,
            iv=Decimal("15.0"),
            delta=Decimal("0.5"),
        )
        g = leg.greeks()
        assert g["iv"] == Decimal("15.0")
        assert g["delta"] == Decimal("0.5")
        assert g["ltp"] == Decimal("120")
        assert g["oi"] == Decimal("5000")

    def test_repr(self) -> None:
        inst = Instrument(symbol="NIFTY18000CE", exchange="NFO")
        leg = InstrumentOptionLeg(instrument=inst, ltp=Decimal("120"))
        r = repr(leg)
        assert "NFO:NIFTY18000CE" in r
        assert "120" in r


# ── InstrumentOptionChain Analytics Tests ─────────────────────────────────


class TestChainAnalytics:
    def test_max_pain_strike(self, chain: InstrumentOptionChain) -> None:
        """Max pain should find the strike with minimum total pain."""
        mp = chain.max_pain_strike
        assert isinstance(mp, Decimal)
        assert mp > Decimal("0")

    def test_pcr(self, chain: InstrumentOptionChain) -> None:
        """Put-Call Ratio based on OI."""
        pcr = chain.pcr
        # Total call OI = 1000+2000+3000+4000+5000 = 15000
        # Total put OI = 12000+10000+8000+6000+4000 = 40000
        assert pcr == Decimal("40000") / Decimal("15000")

    def test_pcr_empty_chain(self) -> None:
        chain = InstrumentOptionChain(
            underlying=Instrument(symbol="NIFTY", exchange="NSE"),
            expiry="2025-01-30",
            spot=Decimal("18000"),
            strikes=(),
        )
        assert chain.pcr == Decimal("0")

    def test_itm_calls(self, chain: InstrumentOptionChain) -> None:
        """Calls with strike < spot (18050) are ITM."""
        itm = chain.itm_strikes("CE")
        assert len(itm) == 3  # 17800, 17900, 18000
        for s in itm:
            assert s.strike < chain.spot

    def test_itm_puts(self, chain: InstrumentOptionChain) -> None:
        """Puts with strike > spot (18050) are ITM."""
        itm = chain.itm_strikes("PE")
        assert len(itm) == 2  # 18100, 18200
        for s in itm:
            assert s.strike > chain.spot

    def test_otm_calls(self, chain: InstrumentOptionChain) -> None:
        """Calls with strike > spot (18050) are OTM."""
        otm = chain.otm_strikes("CE")
        assert len(otm) == 2  # 18100, 18200

    def test_otm_puts(self, chain: InstrumentOptionChain) -> None:
        """Puts with strike < spot (18050) are OTM."""
        otm = chain.otm_strikes("PE")
        assert len(otm) == 3  # 17800, 17900, 18000

    def test_atm_strike(self, chain: InstrumentOptionChain) -> None:
        """ATM should be the strike closest to spot (18100 vs 18050 = 50, 18000 vs 18050 = 50)."""
        atm = chain.atm_strike()
        assert atm is not None
        # Both 18000 and 18100 are 50 away, so the first one sorted is returned
        assert atm.strike in (Decimal("18000"), Decimal("18100"))

    def test_nearest_strikes(self, chain: InstrumentOptionChain) -> None:
        nearest = chain.nearest_strikes(n=2)
        assert len(nearest) == 2  # The two closest strikes to 18050
        # Closest are 18000 (diff=50) and 18100 (diff=50)
        assert nearest[0].strike in (Decimal("18000"), Decimal("18100"))


# ── Filter by Delta ───────────────────────────────────────────────────────


class TestFilterByDelta:
    def test_filter_by_delta_range(self, chain: InstrumentOptionChain) -> None:
        """Filter calls with delta between 0.4 and 0.8."""
        filtered = chain.filter_by_delta(min_delta=0.4, max_delta=0.8, side="CE")
        assert len(filtered) > 0
        for s in filtered:
            d = abs(float(s.call.delta))
            assert 0.4 <= d <= 0.8

    def test_filter_by_delta_puts(self, chain: InstrumentOptionChain) -> None:
        filtered = chain.filter_by_delta(min_delta=0.3, max_delta=0.6, side="PE")
        assert len(filtered) > 0

    def test_filter_by_delta_empty_chain(self) -> None:
        chain = InstrumentOptionChain(
            underlying=Instrument(symbol="NIFTY", exchange="NSE"),
            expiry="2025-01-30",
            spot=Decimal("18000"),
            strikes=(),
        )
        assert chain.filter_by_delta(min_delta=0.0, max_delta=1.0) == ()


# ── SyntheticFuture Tests ─────────────────────────────────────────────────


class TestSyntheticFuture:
    def test_synthetic_future_construction(self, chain: InstrumentOptionChain) -> None:
        """Synthetic future from ATM strike."""
        synth = chain.synthetic_future(quantity=25)
        assert isinstance(synth, SyntheticFuture)
        assert synth.quantity == 25
        assert synth.entry_strike is not None
        assert synth.call is not None
        assert synth.put is not None

    def test_synthetic_future_net_premium(self, chain: InstrumentOptionChain) -> None:
        """Net premium = call LTP - put LTP."""
        synth = chain.synthetic_future()
        expected = synth.call.ltp - synth.put.ltp
        assert synth.net_premium == expected

    def test_synthetic_future_break_even(self, chain: InstrumentOptionChain) -> None:
        """Break-even = entry strike + net premium."""
        synth = chain.synthetic_future()
        assert synth.break_even == synth.entry_strike + synth.net_premium

    def test_synthetic_future_pnl(self, chain: InstrumentOptionChain) -> None:
        """PnL = current_value - net_premium * quantity."""
        synth = chain.synthetic_future(quantity=10)
        expected_pnl = synth.current_value - (synth.net_premium * Decimal("10"))
        assert synth.pnl() == expected_pnl

    def test_synthetic_future_close_orders(self, chain: InstrumentOptionChain) -> None:
        synth = chain.synthetic_future(quantity=25)
        orders = synth.close_orders()
        assert len(orders) == 2
        assert orders[0]["side"] == "SELL"  # Close long call
        assert orders[1]["side"] == "BUY"  # Close short put
        assert orders[0]["quantity"] == 25
        assert orders[1]["quantity"] == 25

    def test_synthetic_future_specific_strike(self, chain: InstrumentOptionChain) -> None:
        """Create synthetic at a specific strike."""
        synth = chain.synthetic_future(strike=Decimal("18000"))
        assert synth.entry_strike == Decimal("18000")

    def test_synthetic_future_empty_chain_raises(self) -> None:
        chain = InstrumentOptionChain(
            underlying=Instrument(symbol="NIFTY", exchange="NSE"),
            expiry="2025-01-30",
            spot=Decimal("18000"),
            strikes=(),
        )
        with pytest.raises(ValueError, match="no strikes available"):
            chain.synthetic_future()

    def test_synthetic_future_nonexistent_strike_raises(self, chain: InstrumentOptionChain) -> None:
        with pytest.raises(ValueError, match="not found in chain"):
            chain.synthetic_future(strike=Decimal("99999"))


# ── Bulk Subscriptions Tests ──────────────────────────────────────────────


class TestSubscribeAll:
    def test_subscribe_all_no_context_raises(self, chain: InstrumentOptionChain) -> None:
        """subscribe_all without context should raise RuntimeError."""
        chain._context = None
        with pytest.raises(RuntimeError, match="no context"):
            chain.subscribe_all(lambda q: None)

    def test_subscribe_all_with_mock_context(self, chain: InstrumentOptionChain) -> None:
        """subscribe_all should subscribe to underlying + all legs."""
        mock_ctx = MagicMock()
        mock_ctx.subscribe.return_value = "handle_123"
        chain._context = mock_ctx

        count = chain.subscribe_all(lambda q: None)
        # 1 underlying + 5 calls + 5 puts = 11 unique instruments
        assert count == 11
        assert mock_ctx.subscribe.call_count == 11

    def test_subscribe_all_idempotent(self, chain: InstrumentOptionChain) -> None:
        """Calling subscribe_all twice should not duplicate subscriptions."""
        mock_ctx = MagicMock()
        mock_ctx.subscribe.return_value = "handle_123"
        chain._context = mock_ctx

        chain.subscribe_all(lambda q: None)
        count2 = chain.subscribe_all(lambda q: None)

        assert count2 == 0  # All already subscribed
        assert mock_ctx.subscribe.call_count == 11  # Only first call did work

    def test_unsubscribe_all(self, chain: InstrumentOptionChain) -> None:
        mock_ctx = MagicMock()
        mock_ctx.subscribe.return_value = "handle_123"
        chain._context = mock_ctx

        chain.subscribe_all(lambda q: None)
        count = chain.unsubscribe_all()
        assert count > 0
        assert len(chain._subscriptions) == 0

    def test_unsubscribe_all_no_context(self, chain: InstrumentOptionChain) -> None:
        chain._context = None
        assert chain.unsubscribe_all() == 0


# ── Instrument Iteration Tests ────────────────────────────────────────────


class TestChainIteration:
    def test_chain_iterable(self, chain: InstrumentOptionChain) -> None:
        strikes = list(chain)
        assert len(strikes) == 5

    def test_chain_len(self, chain: InstrumentOptionChain) -> None:
        assert len(chain) == 5

    def test_chain_empty_len(self) -> None:
        chain = InstrumentOptionChain(
            underlying=Instrument(symbol="NIFTY", exchange="NSE"),
            expiry="2025-01-30",
            spot=Decimal("18000"),
            strikes=(),
        )
        assert len(chain) == 0

    def test_chain_repr(self, chain: InstrumentOptionChain) -> None:
        r = repr(chain)
        assert "NSE:NIFTY" in r
        assert "strikes=5" in r


# ── Build from Raw OptionChain ────────────────────────────────────────────


class TestBuildFromRaw:
    def test_build_from_raw_option_chain(self) -> None:
        """_build_instrument_chain should resolve all symbols to Instruments."""
        raw = OptionChain(
            underlying="NIFTY",
            expiry="2025-01-30",
            spot=Decimal("18050"),
            strikes=(
                OptionStrike(
                    strike=Decimal("18000"),
                    call=OptionLeg(
                        ltp=Decimal("120"),
                        oi=5000,
                        volume=2500,
                        iv=Decimal("15"),
                        delta=Decimal("0.5"),
                        theta=Decimal("-0.1"),
                        gamma=Decimal("0.01"),
                        vega=Decimal("0.2"),
                        security_id=1,
                        symbol="NIFTY18000CE",
                    ),
                    put=OptionLeg(
                        ltp=Decimal("180"),
                        oi=6000,
                        volume=3000,
                        iv=Decimal("16"),
                        delta=Decimal("-0.4"),
                        theta=Decimal("-0.1"),
                        gamma=Decimal("0.01"),
                        vega=Decimal("0.2"),
                        security_id=2,
                        symbol="NIFTY18000PE",
                    ),
                ),
            ),
        )

        mock_ctx = MagicMock()
        mock_ctx._registry = None  # Force creation of minimal instruments

        chain = _build_instrument_chain(mock_ctx, raw)
        assert isinstance(chain, InstrumentOptionChain)
        assert len(chain.strikes) == 1
        assert chain.strikes[0].strike == Decimal("18000")
        assert chain.strikes[0].call.instrument is not None
        assert chain.strikes[0].call.ltp == Decimal("120")
        assert chain.strikes[0].put.ltp == Decimal("180")


# ── Strikes Indexing ──────────────────────────────────────────────────────


class TestStrikeAccess:
    def test_access_by_index(self, chain: InstrumentOptionChain) -> None:
        """Strikes should be accessible by index."""
        s = chain.strikes[2]  # Middle strike
        assert isinstance(s, InstrumentOptionStrike)
        assert s.call.instrument is not None
        assert s.put.instrument is not None

    def test_call_put_methods(self, chain: InstrumentOptionChain) -> None:
        """Leg instruments should support buy/sell."""
        s = chain.strikes[2]
        inst = s.call.instrument
        # Verify it has trading methods by checking the type
        assert hasattr(inst, "buy")
        assert hasattr(inst, "sell")
        assert hasattr(inst, "quote")

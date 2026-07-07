"""Tests for Phase 7: Multi-Leg Order Composition.

Covers:
- StrategyLeg construction
- VerticalSpread (bull call, bear put, etc.)
- Straddle (long/short)
- Strangle (long/short)
- IronCondor
- ComboOrder (custom N-leg builder)
- PnL calculations
- Order placement delegation
- Validation (incompatible legs, wrong sides, etc.)
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from brokers.market.instrument import Instrument
from brokers.market.strategies import (
    ComboOrder,
    IronCondor,
    OptionStrategy,
    Straddle,
    Strangle,
    StrategyLeg,
    VerticalSpread,
)
from brokers_core.domain.enums import Side

# ── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture
def underlying() -> Instrument:
    return Instrument(symbol="NIFTY", exchange="NSE", name="Nifty 50", lot_size=25)


def _make_option(symbol: str, strike: Decimal, opt_type: str) -> Instrument:
    return Instrument(
        symbol=symbol,
        exchange="NFO",
        strike=strike,
        option_type=opt_type,
        lot_size=25,
    )


def _make_provider(ltp: Decimal) -> MagicMock:
    """Create a mock provider that returns a fixed LTP."""
    provider = MagicMock()
    quote = MagicMock()
    quote.ltp = ltp
    provider.quote.return_value = quote
    return provider


# ── StrategyLeg Tests ────────────────────────────────────────────────────


class TestStrategyLeg:
    def test_leg_construction(self) -> None:
        inst = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        leg = StrategyLeg(instrument=inst, side=Side.BUY, quantity=25)
        assert leg.instrument is inst
        assert leg.side == Side.BUY
        assert leg.quantity == 25
        assert leg.ratio == 1  # default

    def test_leg_with_ratio(self) -> None:
        inst = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        leg = StrategyLeg(instrument=inst, side=Side.SELL, quantity=25, ratio=2)
        assert leg.ratio == 2


# ── VerticalSpread Tests ─────────────────────────────────────────────────


class TestVerticalSpread:
    def test_bull_call_spread(self, underlying: Instrument) -> None:
        lower_strike = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        higher_strike = _make_option("NIFTY18100CE", Decimal("18100"), "CE")

        # Attach providers with known premiums
        lower_strike.with_providers(provider=_make_provider(Decimal("100")))
        higher_strike.with_providers(provider=_make_provider(Decimal("50")))

        spread = VerticalSpread(
            underlying=underlying,
            long_leg=lower_strike,
            short_leg=higher_strike,
            quantity=25,
            side="bull_call",
        )

        assert spread.is_call_spread
        assert spread.is_bullish
        assert spread.width == Decimal("100")
        # Net premium: buy 100 (cost), sell 50 (credit) = -50 (net debit)
        assert spread.max_loss == Decimal("50")  # premium paid
        assert spread.max_profit == Decimal("50")  # width - premium

    def test_bear_put_spread(self, underlying: Instrument) -> None:
        lower_strike = _make_option("NIFTY18000PE", Decimal("18000"), "PE")
        higher_strike = _make_option("NIFTY18100PE", Decimal("18100"), "PE")

        lower_strike.with_providers(provider=_make_provider(Decimal("50")))
        higher_strike.with_providers(provider=_make_provider(Decimal("100")))

        spread = VerticalSpread(
            underlying=underlying,
            long_leg=lower_strike,  # buy lower strike put
            short_leg=higher_strike,  # sell higher strike put
            quantity=25,
            side="bear_put",
        )

        assert not spread.is_call_spread
        assert not spread.is_bullish
        assert spread.width == Decimal("100")
        # Net premium: buy 50 (cost), sell 100 (credit) = +50 (net credit)
        assert spread.max_profit == Decimal("50")  # net credit
        assert spread.max_loss == Decimal("50")  # width - credit

    def test_invalid_side_raises(self, underlying: Instrument) -> None:
        call = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        with pytest.raises(ValueError, match="Invalid vertical spread side"):
            VerticalSpread(
                underlying=underlying,
                long_leg=call,
                short_leg=call,
                quantity=25,
                side="invalid",
            )

    def test_mismatched_types_raises(self, underlying: Instrument) -> None:
        call = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        put = _make_option("NIFTY18000PE", Decimal("18000"), "PE")
        with pytest.raises(ValueError, match="same option type"):
            VerticalSpread(
                underlying=underlying,
                long_leg=call,
                short_leg=put,
                quantity=25,
                side="bull_call",
            )

    def test_break_even_bull_call(self, underlying: Instrument) -> None:
        lower_strike = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        higher_strike = _make_option("NIFTY18100CE", Decimal("18100"), "CE")
        lower_strike.with_providers(provider=_make_provider(Decimal("100")))
        higher_strike.with_providers(provider=_make_provider(Decimal("50")))

        spread = VerticalSpread(
            underlying=underlying,
            long_leg=lower_strike,
            short_leg=higher_strike,
            quantity=25,
            side="bull_call",
        )
        assert spread.break_even == [Decimal("18050")]  # lower strike + premium


# ── Straddle Tests ───────────────────────────────────────────────────────


class TestStraddle:
    def test_long_straddle(self, underlying: Instrument) -> None:
        call = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        put = _make_option("NIFTY18000PE", Decimal("18000"), "PE")
        call.with_providers(provider=_make_provider(Decimal("100")))
        put.with_providers(provider=_make_provider(Decimal("80")))

        straddle = Straddle(
            underlying=underlying,
            call_leg=call,
            put_leg=put,
            quantity=25,
            side="long",
        )

        assert straddle.is_long
        assert straddle.strike == Decimal("18000")
        # Premium paid = 100 + 80 = 180
        assert straddle.max_loss == Decimal("180")  # total premium paid

    def test_short_straddle(self, underlying: Instrument) -> None:
        call = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        put = _make_option("NIFTY18000PE", Decimal("18000"), "PE")
        call.with_providers(provider=_make_provider(Decimal("100")))
        put.with_providers(provider=_make_provider(Decimal("80")))

        straddle = Straddle(
            underlying=underlying,
            call_leg=call,
            put_leg=put,
            quantity=25,
            side="short",
        )

        assert not straddle.is_long
        assert straddle.strike == Decimal("18000")
        # Premium received = 100 + 80 = 180
        assert straddle.max_profit == Decimal("180")

    def test_long_straddle_pnl(self, underlying: Instrument) -> None:
        call = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        put = _make_option("NIFTY18000PE", Decimal("18000"), "PE")

        straddle = Straddle(
            underlying=underlying,
            call_leg=call,
            put_leg=put,
            quantity=25,
            side="long",
        )
        straddle._leg_price = lambda leg: Decimal("90")  # mock premium

        # At strike (18000): PnL = 0 - 180 = -180
        assert straddle.pnl_at(Decimal("18000")) == Decimal("-180")
        # Above strike + premium: PnL = (18200 - 18000) - 180 = 20
        assert straddle.pnl_at(Decimal("18200")) == Decimal("20")

    def test_invalid_side_raises(self, underlying: Instrument) -> None:
        call = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        put = _make_option("NIFTY18000PE", Decimal("18000"), "PE")
        with pytest.raises(ValueError, match="Invalid straddle side"):
            Straddle(
                underlying=underlying,
                call_leg=call,
                put_leg=put,
                quantity=25,
                side="invalid",
            )


# ── Strangle Tests ───────────────────────────────────────────────────────


class TestStrangle:
    def test_long_strangle(self, underlying: Instrument) -> None:
        put = _make_option("NIFTY17900PE", Decimal("17900"), "PE")
        call = _make_option("NIFTY18100CE", Decimal("18100"), "CE")
        put.with_providers(provider=_make_provider(Decimal("50")))
        call.with_providers(provider=_make_provider(Decimal("50")))

        strangle = Strangle(
            underlying=underlying,
            call_leg=call,
            put_leg=put,
            quantity=25,
            side="long",
        )

        assert strangle.is_long
        assert strangle.max_loss == Decimal("100")  # 50 + 50

    def test_short_strangle(self, underlying: Instrument) -> None:
        put = _make_option("NIFTY17900PE", Decimal("17900"), "PE")
        call = _make_option("NIFTY18100CE", Decimal("18100"), "CE")
        put.with_providers(provider=_make_provider(Decimal("50")))
        call.with_providers(provider=_make_provider(Decimal("50")))

        strangle = Strangle(
            underlying=underlying,
            call_leg=call,
            put_leg=put,
            quantity=25,
            side="short",
        )

        assert not strangle.is_long
        assert strangle.max_profit == Decimal("100")  # 50 + 50

    def test_invalid_strike_order_raises(self, underlying: Instrument) -> None:
        put = _make_option("NIFTY18100PE", Decimal("18100"), "PE")  # higher strike
        call = _make_option("NIFTY17900CE", Decimal("17900"), "CE")  # lower strike
        with pytest.raises(ValueError, match="put strike < call strike"):
            Strangle(
                underlying=underlying,
                call_leg=call,
                put_leg=put,
                quantity=25,
                side="long",
            )

    def test_long_strangle_pnl(self, underlying: Instrument) -> None:
        put = _make_option("NIFTY17900PE", Decimal("17900"), "PE")
        call = _make_option("NIFTY18100CE", Decimal("18100"), "CE")

        strangle = Strangle(
            underlying=underlying,
            call_leg=call,
            put_leg=put,
            quantity=25,
            side="long",
        )
        strangle._leg_price = lambda leg: Decimal("50")

        # At spot between strikes: max loss = premium
        assert strangle.pnl_at(Decimal("18000")) == Decimal("-100")
        # Below put strike: (17900 - 17800) - 100 = 0
        assert strangle.pnl_at(Decimal("17800")) == Decimal("0")
        # Above call strike: (18200 - 18100) - 100 = 0
        assert strangle.pnl_at(Decimal("18200")) == Decimal("0")


# ── IronCondor Tests ─────────────────────────────────────────────────────


class TestIronCondor:
    def test_iron_condor_construction(self, underlying: Instrument) -> None:
        lp = _make_option("NIFTY17800PE", Decimal("17800"), "PE")
        sp = _make_option("NIFTY17900PE", Decimal("17900"), "PE")
        sc = _make_option("NIFTY18100CE", Decimal("18100"), "CE")
        lc = _make_option("NIFTY18200CE", Decimal("18200"), "CE")

        condor = IronCondor(
            underlying=underlying,
            long_put_leg=lp,
            short_put_leg=sp,
            short_call_leg=sc,
            long_call_leg=lc,
            quantity=25,
        )

        assert len(condor.legs) == 4
        assert condor.legs[0].side == Side.BUY  # long put (wing)
        assert condor.legs[1].side == Side.SELL  # short put (body)
        assert condor.legs[2].side == Side.SELL  # short call (body)
        assert condor.legs[3].side == Side.BUY  # long call (wing)

    def test_invalid_strike_order_raises(self, underlying: Instrument) -> None:
        lp = _make_option("NIFTY17900PE", Decimal("17900"), "PE")  # not lowest
        sp = _make_option("NIFTY17800PE", Decimal("17800"), "PE")
        sc = _make_option("NIFTY18100CE", Decimal("18100"), "CE")
        lc = _make_option("NIFTY18200CE", Decimal("18200"), "CE")

        with pytest.raises(ValueError, match="long_put < short_put"):
            IronCondor(
                underlying=underlying,
                long_put_leg=lp,
                short_put_leg=sp,
                short_call_leg=sc,
                long_call_leg=lc,
                quantity=25,
            )


# ── ComboOrder Tests ─────────────────────────────────────────────────────


class TestComboOrder:
    def test_combo_order_construction(self, underlying: Instrument) -> None:
        leg1 = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        leg2 = _make_option("NIFTY18000PE", Decimal("18000"), "PE")
        leg3 = _make_option("NIFTY17900PE", Decimal("17900"), "PE")

        combo = ComboOrder(
            underlying=underlying,
            legs=[
                StrategyLeg(instrument=leg1, side=Side.BUY, quantity=25),
                StrategyLeg(instrument=leg2, side=Side.BUY, quantity=25),
                StrategyLeg(instrument=leg3, side=Side.SELL, quantity=25),
            ],
            name="custom_butterfly",
        )

        assert len(combo.legs) == 3

    def test_combo_requires_at_least_2_legs(self, underlying: Instrument) -> None:
        leg = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        with pytest.raises(ValueError, match="at least 2 legs"):
            ComboOrder(
                underlying=underlying,
                legs=[StrategyLeg(instrument=leg, side="BUY", quantity=25)],
            )

    def test_combo_place_orders(self, underlying: Instrument) -> None:
        """ComboOrder.place_orders() should delegate to each leg."""
        leg1 = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        leg2 = _make_option("NIFTY18000PE", Decimal("18000"), "PE")

        provider1 = MagicMock()
        provider1.place_order.return_value = {"order_id": "ORD001"}
        provider2 = MagicMock()
        provider2.place_order.return_value = {"order_id": "ORD002"}

        leg1.with_providers(order_provider=provider1)
        leg2.with_providers(order_provider=provider2)

        combo = ComboOrder(
            underlying=underlying,
            legs=[
                StrategyLeg(instrument=leg1, side=Side.BUY, quantity=25),
                StrategyLeg(instrument=leg2, side=Side.SELL, quantity=25),
            ],
            name="test",
        )

        results = combo.place_orders()
        assert len(results) == 2
        assert results[0]["order_id"] == "ORD001"
        assert results[1]["order_id"] == "ORD002"


# ── StrategyLeg Net Premium Tests ────────────────────────────────────────


class TestNetPremium:
    def test_net_premium_buy_only(self) -> None:
        """Strategy with only BUY legs should have negative net premium."""
        underlying = Instrument(symbol="NIFTY", exchange="NSE", lot_size=25)
        leg1 = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        leg2 = _make_option("NIFTY18000PE", Decimal("18000"), "PE")
        leg1.with_providers(provider=_make_provider(Decimal("100")))
        leg2.with_providers(provider=_make_provider(Decimal("80")))

        combo = ComboOrder(
            underlying=underlying,
            legs=[
                StrategyLeg(instrument=leg1, side=Side.BUY, quantity=25),
                StrategyLeg(instrument=leg2, side=Side.BUY, quantity=25),
            ],
        )
        # Net = -100 - 80 = -180 (paid)
        assert combo.net_premium == Decimal("-180")

    def test_strategy_repr(self) -> None:
        underlying = Instrument(symbol="NIFTY", exchange="NSE", lot_size=25)
        leg1 = _make_option("NIFTY18000CE", Decimal("18000"), "CE")
        leg2 = _make_option("NIFTY18000PE", Decimal("18000"), "PE")
        combo = ComboOrder(
            underlying=underlying,
            legs=[
                StrategyLeg(instrument=leg1, side=Side.BUY, quantity=25),
                StrategyLeg(instrument=leg2, side=Side.SELL, quantity=25),
            ],
            name="test",
        )
        r = repr(combo)
        assert "test" in r
        assert "BUY" in r
        assert "NIFTY18000CE" in r

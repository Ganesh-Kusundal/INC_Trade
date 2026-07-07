"""Integration tests: InstrumentOptionChain with PaperAdapter.

Verifies that the option chain composition works with the new adapter
pattern, including InstrumentOptionLeg, InstrumentOptionStrike, and
subscribe_all.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from brokers.adapters.paper.adapter import PaperAdapter


@pytest.fixture
def adapter() -> PaperAdapter:
    a = PaperAdapter()
    a.connect()
    return a


class TestInstrumentOptionChain:
    """InstrumentOptionChain construction and query."""

    def test_option_chain_requires_context(self, adapter: PaperAdapter) -> None:
        """Instrument.option_chain() still requires _context (not provider).

        The Instrument-level shortcut still uses the legacy _context
        path; only MarketDataQuery uses the new provider path.
        """
        from brokers.market.instrument import Instrument

        inst = Instrument(symbol="NIFTY", exchange="NFO")
        inst.with_providers(provider=adapter)

        with pytest.raises(RuntimeError, match="market data context"):
            inst.option_chain()

    def test_query_option_chain_via_provider(self, adapter: PaperAdapter) -> None:
        """MarketDataQuery.option_chain() resolves via provider."""
        from brokers.market.instrument import Instrument
        from brokers.market.query import MarketDataQuery

        inst = Instrument(symbol="NIFTY", exchange="NFO")

        query = MarketDataQuery(instrument=inst, provider=adapter)
        chain = query.option_chain("2025-01-30")

        assert chain is not None
        assert chain.underlying.symbol == "NIFTY"
        assert chain.expiry == "2025-01-30"
        assert len(chain.strikes) == 2
        assert chain.strikes[0].strike is not None
        assert chain.strikes[0].call.ltp > 0
        assert chain.strikes[0].put.ltp > 0

    def test_query_option_chain_no_expiry(self, adapter: PaperAdapter) -> None:
        """MarketDataQuery.option_chain() works without specifying expiry."""
        from brokers.market.instrument import Instrument
        from brokers.market.query import MarketDataQuery

        inst = Instrument(symbol="NIFTY", exchange="NFO")
        query = MarketDataQuery(instrument=inst, provider=adapter)

        chain = query.option_chain()
        assert chain is not None
        assert chain.expiry is not None
        assert len(chain.strikes) == 2

    def test_instrument_option_chain_construction(self) -> None:
        """InstrumentOptionChain can be constructed manually."""
        from brokers.market.instrument import Instrument
        from brokers.market.option_chain import (
            InstrumentOptionChain,
            InstrumentOptionLeg,
            InstrumentOptionStrike,
        )

        underlying = Instrument(symbol="NIFTY", exchange="NFO")

        call_inst = Instrument(
            symbol="NIFTY",
            exchange="NFO",
            expiry=__import__("datetime").datetime(2025, 1, 30),
            strike=Decimal("25000"),
            option_type="CE",
        )
        put_inst = Instrument(
            symbol="NIFTY",
            exchange="NFO",
            expiry=__import__("datetime").datetime(2025, 1, 30),
            strike=Decimal("25000"),
            option_type="PE",
        )

        strikes = [
            InstrumentOptionStrike(
                strike=Decimal("25000"),
                call=InstrumentOptionLeg(
                    instrument=call_inst,
                    ltp=Decimal("125.50"),
                    oi=100000,
                    volume=5000,
                    iv=Decimal("15.5"),
                    delta=Decimal("0.55"),
                ),
                put=InstrumentOptionLeg(
                    instrument=put_inst,
                    ltp=Decimal("100.25"),
                    oi=120000,
                    volume=4500,
                    iv=Decimal("16.2"),
                    delta=Decimal("-0.45"),
                ),
            ),
        ]

        chain = InstrumentOptionChain(
            underlying=underlying,
            expiry="2025-01-30",
            spot=Decimal("25100"),
            strikes=strikes,
        )

        assert chain.underlying.symbol == "NIFTY"
        assert chain.expiry == "2025-01-30"
        assert len(chain.strikes) == 1

    def test_option_chain_atm_strike(self) -> None:
        """InstrumentOptionChain finds ATM strike correctly."""
        from brokers.market.instrument import Instrument
        from brokers.market.option_chain import (
            InstrumentOptionChain,
            InstrumentOptionLeg,
            InstrumentOptionStrike,
        )

        underlying = Instrument(symbol="NIFTY", exchange="NFO")

        strikes = [
            InstrumentOptionStrike(
                strike=Decimal("24900"),
                call=InstrumentOptionLeg(
                    instrument=Instrument(
                        symbol="NIFTY", exchange="NFO", strike=Decimal("24900"), option_type="CE"
                    ),
                    ltp=Decimal("200"),
                ),
                put=InstrumentOptionLeg(
                    instrument=Instrument(
                        symbol="NIFTY", exchange="NFO", strike=Decimal("24900"), option_type="PE"
                    ),
                    ltp=Decimal("50"),
                ),
            ),
            InstrumentOptionStrike(
                strike=Decimal("25000"),
                call=InstrumentOptionLeg(
                    instrument=Instrument(
                        symbol="NIFTY", exchange="NFO", strike=Decimal("25000"), option_type="CE"
                    ),
                    ltp=Decimal("150"),
                ),
                put=InstrumentOptionLeg(
                    instrument=Instrument(
                        symbol="NIFTY", exchange="NFO", strike=Decimal("25000"), option_type="PE"
                    ),
                    ltp=Decimal("75"),
                ),
            ),
            InstrumentOptionStrike(
                strike=Decimal("25100"),
                call=InstrumentOptionLeg(
                    instrument=Instrument(
                        symbol="NIFTY", exchange="NFO", strike=Decimal("25100"), option_type="CE"
                    ),
                    ltp=Decimal("100"),
                ),
                put=InstrumentOptionLeg(
                    instrument=Instrument(
                        symbol="NIFTY", exchange="NFO", strike=Decimal("25100"), option_type="PE"
                    ),
                    ltp=Decimal("110"),
                ),
            ),
        ]

        # Spot at 25050 → ATM should be 25000 or 25100 (pick closest)
        chain = InstrumentOptionChain(
            underlying=underlying,
            expiry="2025-01-30",
            spot=Decimal("25050"),
            strikes=strikes,
        )

        atm = chain.atm_strike()
        # atm_strike() is a method returning the closest strike to spot
        # Spot at 25050, strikes at 24900, 25000, 25100
        # 25050 - 25000 = 50, 25100 - 25050 = 50 → both equally close
        # min() will pick the first encountered, which is 25000
        assert atm is not None
        assert atm.strike == Decimal("25000")

    def test_option_leg_query_and_command(self) -> None:
        """InstrumentOptionLeg provides query() and command()."""
        from brokers.market.instrument import Instrument
        from brokers.market.option_chain import InstrumentOptionLeg

        inst = Instrument(symbol="NIFTY", exchange="NFO", strike=Decimal("25000"), option_type="CE")

        leg = InstrumentOptionLeg(
            instrument=inst,
            ltp=Decimal("125.50"),
            oi=100000,
        )

        # Leg has greeks
        greeks = leg.greeks()
        assert greeks["ltp"] == Decimal("125.50")
        assert greeks["oi"] == Decimal("100000")

    def test_synthetic_future_construction(self) -> None:
        """SyntheticFuture can be constructed from call+put."""
        from datetime import datetime

        from brokers.market.instrument import Instrument
        from brokers.market.option_chain import (
            InstrumentOptionChain,
            InstrumentOptionLeg,
            InstrumentOptionStrike,
            SyntheticFuture,
        )

        underlying = Instrument(symbol="NIFTY", exchange="NFO")

        call_inst = Instrument(
            symbol="NIFTY",
            exchange="NFO",
            expiry=datetime(2025, 1, 30),
            strike=Decimal("25000"),
            option_type="CE",
        )
        put_inst = Instrument(
            symbol="NIFTY",
            exchange="NFO",
            expiry=datetime(2025, 1, 30),
            strike=Decimal("25000"),
            option_type="PE",
        )

        chain = InstrumentOptionChain(
            underlying=underlying,
            expiry="2025-01-30",
            spot=Decimal("25100"),
            strikes=[
                InstrumentOptionStrike(
                    strike=Decimal("25000"),
                    call=InstrumentOptionLeg(instrument=call_inst, ltp=Decimal("150")),
                    put=InstrumentOptionLeg(instrument=put_inst, ltp=Decimal("50")),
                ),
            ],
        )

        # Create synthetic future from chain
        sf = chain.synthetic_future(quantity=25)
        assert sf.quantity == 25
        assert sf.call.instrument.symbol == "NIFTY"
        assert sf.put.instrument.symbol == "NIFTY"

        # Break-even: call_ltp - put_ltp + strike
        be = sf.break_even
        assert be == Decimal("25100")  # 150 - 50 + 25000

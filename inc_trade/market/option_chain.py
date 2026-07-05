"""InstrumentOptionChain — OptionChain composed of rich Instrument references.

The raw OptionChain entity uses string symbols for legs. This module
wraps it and resolves each leg to a real Instrument object from the
registry, enabling ``option_chain.strikes[0].call.instrument.quote()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class InstrumentOptionLeg:
    """A single leg (call or put) in an instrument-based option chain.

    Attributes:
        instrument: Rich Instrument reference (not a string symbol).
        ltp: Last traded price.
        oi: Open interest.
        volume: Traded volume.
        iv: Implied volatility.
        delta: Option delta.
    """

    instrument: Any  # Instrument (rich reference)
    ltp: Decimal = Decimal("0")
    oi: int = 0
    volume: int = 0
    iv: Decimal = Decimal("0")
    delta: Decimal = Decimal("0")

    def greeks(self) -> dict[str, Decimal]:
        """Return available Greeks as a dict."""
        return {
            "iv": self.iv,
            "delta": self.delta,
            "ltp": self.ltp,
            "oi": Decimal(str(self.oi)),
        }


@dataclass(frozen=True)
class InstrumentOptionStrike:
    """A single strike row in an instrument-based option chain.

    Attributes:
        strike: Strike price.
        call: Call option leg (CE).
        put: Put option leg (PE).
    """

    strike: Decimal
    call: InstrumentOptionLeg
    put: InstrumentOptionLeg


class InstrumentOptionChain:
    """Option chain composed of rich Instrument references.

    Wraps a raw OptionChain and resolves each leg's instrument from
    the registry. Provides filtering, max-pain, and PCR calculations.

    Attributes:
        underlying: The underlying Instrument (not a string).
        expiry: Expiry date string.
        spot: Current spot price of underlying.
        strikes: Tuple of InstrumentOptionStrike rows.
    """

    def __init__(
        self,
        underlying: Any,
        expiry: str,
        spot: Decimal,
        strikes: tuple[InstrumentOptionStrike, ...],
    ) -> None:
        object.__setattr__(self, "underlying", underlying)
        object.__setattr__(self, "expiry", expiry)
        object.__setattr__(self, "spot", spot)
        object.__setattr__(self, "strikes", strikes)

    # Allow frozen-dataclass-like attribute access
    underlying: Any
    expiry: str
    spot: Decimal
    strikes: tuple[InstrumentOptionStrike, ...]

    @property
    def max_pain_strike(self) -> Decimal:
        """Calculate the max-pain strike price.

        Max pain is the strike price where the total P&L of all
        option holders (buyers) is maximally negative — i.e., the
        strike where option writers pay out the least.
        """
        if not self.strikes:
            return Decimal("0")

        min_pain = None
        max_pain_strike = Decimal("0")

        for candidate in self.strikes:
            total_pain = Decimal("0")
            for s in self.strikes:
                # Call writers pain: if spot > strike, call ITM
                if s.call.instrument and s.strike < candidate.strike:
                    total_pain += (candidate.strike - s.strike) * Decimal(str(s.call.oi))
                # Put writers pain: if spot < strike, put ITM
                if s.put.instrument and s.strike > candidate.strike:
                    total_pain += (s.strike - candidate.strike) * Decimal(str(s.put.oi))

            if min_pain is None or total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = candidate.strike

        return max_pain_strike

    @property
    def pcr(self) -> Decimal:
        """Put-Call Ratio (PCR) based on open interest.

        PCR > 1 indicates bearish sentiment (more puts than calls).
        PCR < 1 indicates bullish sentiment.
        """
        total_call_oi = sum(s.call.oi for s in self.strikes)
        total_put_oi = sum(s.put.oi for s in self.strikes)
        if total_call_oi > 0:
            return Decimal(str(total_put_oi)) / Decimal(str(total_call_oi))
        return Decimal("0")

    def itm_strikes(self, side: str = "CE") -> tuple[InstrumentOptionStrike, ...]:
        """Get in-the-money strikes for the given side.

        Args:
            side: "CE" for calls, "PE" for puts.
        """
        if side.upper() == "CE":
            return tuple(s for s in self.strikes if s.strike < self.spot)
        return tuple(s for s in self.strikes if s.strike > self.spot)

    def otm_strikes(self, side: str = "CE") -> tuple[InstrumentOptionStrike, ...]:
        """Get out-of-the-money strikes for the given side.

        Args:
            side: "CE" for calls, "PE" for puts.
        """
        if side.upper() == "CE":
            return tuple(s for s in self.strikes if s.strike > self.spot)
        return tuple(s for s in self.strikes if s.strike < self.spot)

    def nearest_strikes(self, n: int = 5) -> tuple[InstrumentOptionStrike, ...]:
        """Get the N strikes nearest to the current spot price.

        Args:
            n: Number of strikes on each side (default 5).

        Returns:
            Tuple of up to 2*N strikes centered around ATM.
        """
        if not self.strikes:
            return ()
        sorted_strikes = sorted(self.strikes, key=lambda s: abs(s.strike - self.spot))
        return tuple(sorted_strikes[:n])

    def __repr__(self) -> str:
        return (
            f"InstrumentOptionChain("
            f"underlying={self.underlying.symbol if hasattr(self.underlying, 'symbol') else self.underlying}, "
            f"expiry={self.expiry!r}, "
            f"strikes={len(self.strikes)})"
        )

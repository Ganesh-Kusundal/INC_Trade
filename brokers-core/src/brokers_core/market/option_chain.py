"""InstrumentOptionChain — OptionChain composed of rich Instrument references.

The raw ``OptionChain`` entity uses string symbols for legs. This module
wraps it and resolves each leg to a real ``Instrument`` object, enabling::

    chain = inst.option_chain("2025-01-30")
    chain.strikes[0].call.instrument.quote()
    chain.strikes[0].put.instrument.buy(qty=25)

Additional capabilities:
    - ``subscribe_all(callback)`` — one-call subscribe to all legs + underlying
    - ``synthetic_future(quantity)`` — construct a synthetic futures position
    - ``refresh()`` — refetch the chain with updated market data
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from brokers_core.domain.entities import OptionChain as RawOptionChain

logger = logging.getLogger(__name__)


# ── Data Classes ──────────────────────────────────────────────────────────


class InstrumentOptionLeg:
    """A single leg (call or put) in an instrument-based option chain.

    Unlike a frozen dataclass, this is a mutable object so that
    ``refresh()`` can update LTP, OI, and Greeks in-place without
    rebuilding the tree.

    Attributes:
        instrument: Rich Instrument reference (not a string symbol).
        ltp: Last traded price.
        oi: Open interest.
        volume: Traded volume.
        iv: Implied volatility.
        delta: Option delta.
    """

    def __init__(
        self,
        instrument: Any,
        ltp: Decimal = Decimal("0"),
        oi: int = 0,
        volume: int = 0,
        iv: Decimal = Decimal("0"),
        delta: Decimal = Decimal("0"),
    ) -> None:
        self.instrument = instrument
        self.ltp = ltp
        self.oi = oi
        self.volume = volume
        self.iv = iv
        self.delta = delta

    def greeks(self) -> dict[str, Decimal]:
        """Return available Greeks as a dict."""
        return {
            "iv": self.iv,
            "delta": self.delta,
            "ltp": self.ltp,
            "oi": Decimal(str(self.oi)),
        }

    def __repr__(self) -> str:
        sym = getattr(self.instrument, "composite_key", str(self.instrument))
        return f"InstrumentOptionLeg({sym}, ltp={self.ltp}, oi={self.oi})"


class InstrumentOptionStrike:
    """A single strike row in an instrument-based option chain.

    Attributes:
        strike: Strike price.
        call: Call option leg (CE).
        put: Put option leg (PE).
    """

    def __init__(
        self,
        strike: Decimal,
        call: InstrumentOptionLeg,
        put: InstrumentOptionLeg,
    ) -> None:
        self.strike = strike
        self.call = call
        self.put = put

    def __repr__(self) -> str:
        return (
            f"InstrumentOptionStrike("
            f"strike={self.strike}, "
            f"call_ltp={self.call.ltp}, "
            f"put_ltp={self.put.ltp})"
        )


# ── Synthetic Future ──────────────────────────────────────────────────────


class SyntheticFuture:
    """A synthetic futures position constructed from options.

    A synthetic long future is: **buy ATM call + sell ATM put** at the
    same strike and expiry. This replicates the payoff of a futures
    contract.

    Attributes:
        underlying: The underlying Instrument.
        expiry: Expiry date string.
        entry_strike: Strike price at which the synthetic was constructed.
        call: The long call InstrumentOptionLeg.
        put: The short put InstrumentOptionLeg.
        quantity: Number of units (multiplier for position sizing).
        net_premium: Net premium paid/received (positive = debit).
    """

    def __init__(
        self,
        underlying: Any,
        expiry: str,
        entry_strike: Decimal,
        call_leg: InstrumentOptionLeg,
        put_leg: InstrumentOptionLeg,
        quantity: int = 1,
    ) -> None:
        self.underlying = underlying
        self.expiry = expiry
        self.entry_strike = entry_strike
        self.call = call_leg
        self.put = put_leg
        self.quantity = quantity
        self.net_premium = call_leg.ltp - put_leg.ltp  # Long call premium - short put premium

    @property
    def break_even(self) -> Decimal:
        """Break-even point for the synthetic future."""
        return self.entry_strike + self.net_premium

    @property
    def current_value(self) -> Decimal:
        """Current mark-to-market value of the position.

        Value = (call_ltp - put_ltp) * quantity
        """
        return (self.call.ltp - self.put.ltp) * Decimal(str(self.quantity))

    def pnl(self) -> Decimal:
        """Profit or loss from the synthetic position.

        PnL = current_value - net_premium * quantity
        """
        return self.current_value - (self.net_premium * Decimal(str(self.quantity)))

    def close_orders(self) -> list[dict[str, Any]]:
        """Generate orders to close the synthetic position.

        Returns:
            List of order dicts (one to sell the call, one to buy back the put).
        """
        return [
            {
                "instrument": self.call.instrument,
                "side": "SELL",
                "quantity": self.quantity,
                "order_type": "MARKET",
                "tag": "synthetic_close_call",
            },
            {
                "instrument": self.put.instrument,
                "side": "BUY",
                "quantity": self.quantity,
                "order_type": "MARKET",
                "tag": "synthetic_close_put",
            },
        ]

    def __repr__(self) -> str:
        sym = getattr(self.underlying, "composite_key", str(self.underlying))
        return (
            f"SyntheticFuture("
            f"underlying={sym}, "
            f"strike={self.entry_strike}, "
            f"expiry={self.expiry!r}, "
            f"qty={self.quantity})"
        )


# ── Instrument Option Chain ────────────────────────────────────────────────


class InstrumentOptionChain:
    """Option chain composed of rich Instrument references.

    Wraps a raw ``OptionChain`` and resolves each leg's instrument from
    the registry. Provides filtering, max-pain, PCR calculations, and
    batch operations on all legs.

    Attributes:
        underlying: The underlying Instrument (not a string).
        expiry: Expiry date string.
        spot: Current spot price of underlying.
        strikes: Tuple of InstrumentOptionStrike rows.
        _context: MarketDataContext reference (for streaming subscriptions).
    """

    def __init__(
        self,
        underlying: Any,
        expiry: str,
        spot: Decimal,
        strikes: tuple[InstrumentOptionStrike, ...],
        context: Any = None,
    ) -> None:
        self.underlying = underlying
        self.expiry = expiry
        self.spot = spot
        self.strikes = strikes
        self._context = context

        # Tracks active subscriptions for subscribe_all/unsubscribe_all
        self._subscriptions: list[Any] = []
        self._subscribed_instruments: set[str] = set()

    # ── Analytics ─────────────────────────────────────────────────────────

    @property
    def max_pain_strike(self) -> Decimal:
        """Calculate the max-pain strike price.

        Max pain is the strike price where the total P&L of all
        option holders (buyers) is maximally negative — i.e., the
        strike where option writers pay out the least.
        """
        if not self.strikes:
            return Decimal("0")

        min_pain: Decimal | None = None
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

    def atm_strike(self) -> InstrumentOptionStrike | None:
        """Get the at-the-money strike (closest to spot).

        Returns:
            The ATM strike row, or None if no strikes available.
        """
        if not self.strikes:
            return None
        return min(self.strikes, key=lambda s: abs(s.strike - self.spot))

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

    def filter_by_delta(
        self,
        min_delta: float = 0.0,
        max_delta: float = 1.0,
        side: str | None = None,
    ) -> tuple[InstrumentOptionStrike, ...]:
        """Filter strikes by delta range.

        Args:
            min_delta: Minimum delta (absolute value).
            max_delta: Maximum delta (absolute value).
            side: 'CE' for calls only, 'PE' for puts only, None for both.

        Returns:
            Filtered tuple of strikes.
        """
        results: list[InstrumentOptionStrike] = []
        for s in self.strikes:
            if side in (None, "CE"):
                d = abs(float(s.call.delta)) if s.call.delta else 0.0
                if min_delta <= d <= max_delta and s not in results:
                    results.append(s)
            if side in (None, "PE"):
                d = abs(float(s.put.delta)) if s.put.delta else 0.0
                if min_delta <= d <= max_delta and s not in results:
                    results.append(s)
        return tuple(results)

    # ── Synthetic Futures ────────────────────────────────────────────────

    def synthetic_future(
        self,
        quantity: int = 1,
        strike: Decimal | None = None,
    ) -> SyntheticFuture:
        """Construct a synthetic futures position.

        A synthetic long future is: **buy ATM call + sell ATM put** at the
        same strike and expiry. If no strike is provided, the ATM strike
        is used automatically.

        Args:
            quantity: Number of units (lot multiplier).
            strike: Strike price for the synthetic. If None, uses ATM.

        Returns:
            A :class:`SyntheticFuture` describing the position.

        Raises:
            ValueError: If no strikes are available or ATM strike not found.
        """
        if not self.strikes:
            raise ValueError("Cannot create synthetic future: no strikes available")

        target_strike: Decimal
        if strike is not None:
            target_strike = strike
        else:
            atm = self.atm_strike()
            if atm is None:
                raise ValueError("Cannot create synthetic future: ATM strike not found")
            target_strike = atm.strike

        # Find the target strike row
        strike_row = next((s for s in self.strikes if s.strike == target_strike), None)
        if strike_row is None:
            raise ValueError(f"Strike {target_strike} not found in chain")

        return SyntheticFuture(
            underlying=self.underlying,
            expiry=self.expiry,
            entry_strike=target_strike,
            call_leg=strike_row.call,
            put_leg=strike_row.put,
            quantity=quantity,
        )

    # ── Bulk Subscriptions ───────────────────────────────────────────────

    def subscribe_all(self, callback: Callable[[Any], Any]) -> int:
        """Subscribe to live market data for ALL instruments in the chain.

        Subscribes to:
        - The underlying instrument
        - Every call leg instrument
        - Every put leg instrument

        Duplicate subscriptions are tracked by composite key so that
        calling ``subscribe_all`` multiple times only subscribes each
        instrument once.

        Args:
            callback: Callable invoked with each new Quote/ tick.

        Returns:
            Number of unique instruments subscribed.

        Raises:
            RuntimeError: If no context is available for subscription.
        """
        if self._context is None:
            raise RuntimeError(
                "Cannot subscribe: InstrumentOptionChain has no context. "
                "Obtain chains via MarketDataContext.option_chain()."
            )

        instruments: list[Any] = [self.underlying]
        for s in self.strikes:
            if s.call.instrument is not None:
                instruments.append(s.call.instrument)
            if s.put.instrument is not None:
                instruments.append(s.put.instrument)

        count = 0
        for inst in instruments:
            key = getattr(inst, "composite_key", id(inst))
            if key not in self._subscribed_instruments:
                handle = self._context.subscribe(
                    getattr(inst, "symbol", ""),
                    getattr(inst, "exchange", "NFO"),
                    callback,
                )
                self._subscriptions.append(handle)
                self._subscribed_instruments.add(key)
                count += 1

        logger.info(
            "subscribe_all: %d instruments subscribed for %s",
            count,
            getattr(self.underlying, "composite_key", str(self.underlying)),
        )
        return count

    def unsubscribe_all(self) -> int:
        """Unsubscribe all instruments previously subscribed via ``subscribe_all``.

        Returns:
            Number of subscriptions removed.
        """
        if self._context is None:
            return 0

        count = 0
        for s in self.strikes:
            for leg in (s.call, s.put):
                if leg.instrument is not None:
                    key = getattr(leg.instrument, "composite_key", id(leg.instrument))
                    if key in self._subscribed_instruments:
                        try:
                            self._context.unsubscribe(
                                getattr(leg.instrument, "symbol", ""),
                                getattr(leg.instrument, "exchange", "NFO"),
                            )
                            count += 1
                        except Exception:
                            logger.warning("unsubscribe_all: failed for %s", key)

        # Also unsubscribe underlying
        key = getattr(self.underlying, "composite_key", id(self.underlying))
        if key in self._subscribed_instruments:
            try:
                self._context.unsubscribe(
                    getattr(self.underlying, "symbol", ""),
                    getattr(self.underlying, "exchange", "NFO"),
                )
                count += 1
            except Exception:
                pass

        self._subscriptions.clear()
        self._subscribed_instruments.clear()
        return count

    # ── Refresh ──────────────────────────────────────────────────────────

    def refresh(self) -> InstrumentOptionChain:
        """Refetch the option chain with updated market data.

        Returns:
            A new ``InstrumentOptionChain`` with fresh strike data.
            The underlying Instrument identity is preserved.
        """
        if self._context is None:
            raise RuntimeError("Cannot refresh: InstrumentOptionChain has no context.")

        raw = self._context.option_chain_raw(
            getattr(self.underlying, "symbol", ""),
            getattr(self.underlying, "exchange", "NFO"),
            expiry=self.expiry,
        )
        if raw is None:
            raise RuntimeError("Failed to refresh option chain")

        # Re-resolve the chain with existing instruments where possible
        return _build_instrument_chain(self._context, raw)

    # ── Iterator ─────────────────────────────────────────────────────────

    def __iter__(self):
        return iter(self.strikes)

    def __len__(self) -> int:
        return len(self.strikes)

    def __repr__(self) -> str:
        sym = getattr(self.underlying, "composite_key", str(self.underlying))
        return (
            f"InstrumentOptionChain("
            f"underlying={sym}, "
            f"expiry={self.expiry!r}, "
            f"strikes={len(self.strikes)})"
        )


# ── Builder ────────────────────────────────────────────────────────────────


def _resolve_instrument(
    context: Any,
    symbol: str,
    exchange: str,
) -> Any:
    """Resolve a symbol to an Instrument via the context's registry.

    Falls back to creating a minimal instrument if the registry
    doesn't have one cached.
    """
    registry = getattr(context, "_registry", None)
    if registry is not None:
        key = f"{exchange}:{symbol}"
        inst = registry.get(key)
        if inst is not None:
            return inst

    # Create a minimal instrument
    from brokers_core.market.factory import InstrumentFactory

    return InstrumentFactory.create(
        symbol=symbol,
        exchange=exchange,
        context=context,
    )


def _build_instrument_chain(
    context: Any,
    raw: RawOptionChain,
) -> InstrumentOptionChain:
    """Build an InstrumentOptionChain from a raw domain OptionChain.

    Resolves each leg's symbol into a rich Instrument using the
    context's registry.
    """
    underlying_inst = _resolve_instrument(context, raw.underlying, "NSE")

    strikes: list[InstrumentOptionStrike] = []
    for raw_strike in raw.strikes:
        call_inst = _resolve_instrument(context, raw_strike.call.symbol, "NFO")
        put_inst = _resolve_instrument(context, raw_strike.put.symbol, "NFO")

        call_leg = InstrumentOptionLeg(
            instrument=call_inst,
            ltp=raw_strike.call.ltp or Decimal("0"),
            oi=raw_strike.call.oi,
            volume=raw_strike.call.volume,
            iv=raw_strike.call.iv,
            delta=raw_strike.call.delta,
        )
        put_leg = InstrumentOptionLeg(
            instrument=put_inst,
            ltp=raw_strike.put.ltp or Decimal("0"),
            oi=raw_strike.put.oi,
            volume=raw_strike.put.volume,
            iv=raw_strike.put.iv,
            delta=raw_strike.put.delta,
        )
        strikes.append(
            InstrumentOptionStrike(
                strike=raw_strike.strike,
                call=call_leg,
                put=put_leg,
            )
        )

    return InstrumentOptionChain(
        underlying=underlying_inst,
        expiry=raw.expiry,
        spot=raw.spot,
        strikes=tuple(strikes),
        context=context,
    )

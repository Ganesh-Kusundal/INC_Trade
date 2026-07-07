"""OptionChain — aggregate root for option chain data.

Each option within the chain is a full :class:`Instrument` (with provider
injected).  The chain provides filtering by moneyness (ATM, ITM, OTM),
calls/puts, expiries, and greeks aggregation.

Also includes :class:`FutureChain` for futures contracts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from brokers.domain.enums import AssetClass, OptionType
from brokers.domain.values import Greeks

if TYPE_CHECKING:
    from brokers.domain.instrument import Instrument
    from brokers.provider.protocol import Provider


@dataclass(frozen=True, slots=True)
class OptionContract:
    """A single option contract within a chain.

    Each contract carries its greeks (typed, not dict) and a reference
    to the instrument it represents.
    """

    strike: Decimal
    option_type: OptionType
    expiry: date
    symbol: str
    ltp: Decimal | None = None
    oi: int | None = None
    volume: int | None = None
    iv: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    greeks: Greeks | None = None

    @property
    def is_call(self) -> bool:
        return self.option_type == OptionType.CALL

    @property
    def is_put(self) -> bool:
        return self.option_type == OptionType.PUT


class OptionChain:
    """Aggregate root for option chain data.

    Owns a collection of :class:`OptionContract` values organized by
    expiry and strike.  Provides filtering by moneyness.

    Each option contract CAN be materialized into a full
    :class:`Instrument` via ``as_instrument()`` — but only on demand,
    not eagerly (performance).
    """

    __slots__ = ("_contracts", "_expiries", "_provider", "_spot", "_strikes", "_underlying")

    def __init__(
        self,
        underlying: Instrument,
        *,
        contracts: list[OptionContract],
        spot: Decimal | None = None,
        provider: Provider | None = None,
    ) -> None:
        self._underlying = underlying
        self._contracts = contracts
        self._spot = spot
        self._provider = provider
        # Build sorted unique strike list and expiry list
        self._strikes = sorted({c.strike for c in contracts})
        self._expiries = sorted({c.expiry for c in contracts})

    # ── Properties ───────────────────────────────────────────────────

    @property
    def underlying(self) -> Instrument:
        return self._underlying

    @property
    def spot(self) -> Decimal | None:
        return self._spot

    @property
    def strikes(self) -> list[Decimal]:
        """Sorted list of all strikes."""
        return list(self._strikes)

    @property
    def expiries(self) -> list[date]:
        """Sorted list of all expiry dates."""
        return list(self._expiries)

    @property
    def contracts(self) -> list[OptionContract]:
        """All option contracts."""
        return list(self._contracts)

    @property
    def contract_count(self) -> int:
        return len(self._contracts)

    # ── Filtering ────────────────────────────────────────────────────

    def calls(self, expiry: date | None = None) -> list[OptionContract]:
        """All call options, optionally filtered by expiry."""
        return [
            c for c in self._contracts
            if c.is_call and (expiry is None or c.expiry == expiry)
        ]

    def puts(self, expiry: date | None = None) -> list[OptionContract]:
        """All put options, optionally filtered by expiry."""
        return [
            c for c in self._contracts
            if c.is_put and (expiry is None or c.expiry == expiry)
        ]

    def atm(self, spot: Decimal | None = None) -> OptionContract | None:
        """Find the at-the-money option (closest strike to spot).

        Returns the call option closest to the spot.  Use ``atm_call()``
        or ``atm_put()`` for specific option types.
        """
        s = spot or self._spot
        if s is None or not self._strikes:
            return None
        # Find closest strike
        closest_strike = min(self._strikes, key=lambda k: abs(k - s))
        # Return first call at that strike
        calls_at_strike = [c for c in self._contracts if c.strike == closest_strike and c.is_call]
        return calls_at_strike[0] if calls_at_strike else None

    def atm_call(self, spot: Decimal | None = None) -> OptionContract | None:
        """Find the ATM call option."""
        s = spot or self._spot
        if s is None or not self._strikes:
            return None
        closest = min(self._strikes, key=lambda k: abs(k - s))
        calls = [c for c in self._contracts if c.strike == closest and c.is_call]
        return calls[0] if calls else None

    def atm_put(self, spot: Decimal | None = None) -> OptionContract | None:
        """Find the ATM put option."""
        s = spot or self._spot
        if s is None or not self._strikes:
            return None
        closest = min(self._strikes, key=lambda k: abs(k - s))
        puts = [c for c in self._contracts if c.strike == closest and c.is_put]
        return puts[0] if puts else None

    def itm_calls(self, spot: Decimal | None = None) -> list[OptionContract]:
        """In-the-money call options (strike < spot)."""
        s = spot or self._spot
        if s is None:
            return []
        return [c for c in self._contracts if c.is_call and c.strike < s]

    def itm_puts(self, spot: Decimal | None = None) -> list[OptionContract]:
        """In-the-money put options (strike > spot)."""
        s = spot or self._spot
        if s is None:
            return []
        return [c for c in self._contracts if c.is_put and c.strike > s]

    def otm_calls(self, spot: Decimal | None = None) -> list[OptionContract]:
        """Out-of-the-money call options (strike > spot)."""
        s = spot or self._spot
        if s is None:
            return []
        return [c for c in self._contracts if c.is_call and c.strike > s]

    def otm_puts(self, spot: Decimal | None = None) -> list[OptionContract]:
        """Out-of-the-money put options (strike < spot)."""
        s = spot or self._spot
        if s is None:
            return []
        return [c for c in self._contracts if c.is_put and c.strike < s]

    # ── Aggregations ─────────────────────────────────────────────────

    def total_call_oi(self, expiry: date | None = None) -> int:
        """Total open interest across all calls."""
        return sum(c.oi or 0 for c in self.calls(expiry))

    def total_put_oi(self, expiry: date | None = None) -> int:
        """Total open interest across all puts."""
        return sum(c.oi or 0 for c in self.puts(expiry))

    def pcr(self, expiry: date | None = None) -> Decimal | None:
        """Put-Call Ratio (total put OI / total call OI).

        Returns None if call OI is zero.
        """
        call_oi = self.total_call_oi(expiry)
        if call_oi == 0:
            return None
        put_oi = self.total_put_oi(expiry)
        return Decimal(str(put_oi)) / Decimal(str(call_oi))

    # ── Materialize option as Instrument ─────────────────────────────

    def as_instrument(self, contract: OptionContract) -> Instrument | None:
        """Materialize an OptionContract as a full Instrument.

        Requires the provider to be set (done by the Broker factory).
        Returns None if no provider is available.
        """
        if self._provider is None:
            return None
        from brokers.domain.instrument import Instrument

        return Instrument(
            symbol=contract.symbol,
            exchange=self._underlying.exchange,
            asset_class=AssetClass.OPTION,
            provider=self._provider,
            expiry=contract.expiry,
            strike=contract.strike,
            option_type=contract.option_type,
        )

    def __repr__(self) -> str:
        return f"OptionChain({self._underlying.symbol}, {self.contract_count} contracts)"


# ── Future chain ───────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class FutureContract:
    """Single futures contract within a chain."""

    symbol: str
    expiry: date
    lot_size: int = 1
    ltp: Decimal | None = None
    oi: int | None = None
    underlying: str = ""


class FutureChain:
    """Aggregate root for futures chain data."""

    __slots__ = ("_contracts", "_expiries", "_underlying")

    def __init__(
        self,
        underlying: Instrument,
        *,
        contracts: list[FutureContract],
    ) -> None:
        self._underlying = underlying
        self._contracts = contracts
        self._expiries = sorted({c.expiry for c in contracts})

    @property
    def underlying(self) -> Instrument:
        return self._underlying

    @property
    def expiries(self) -> list[date]:
        return list(self._expiries)

    @property
    def contracts(self) -> list[FutureContract]:
        return list(self._contracts)

    @property
    def contract_count(self) -> int:
        return len(self._contracts)

    def near_month(self) -> FutureContract | None:
        """The nearest expiry futures contract."""
        if not self._contracts:
            return None
        return min(self._contracts, key=lambda c: c.expiry)

    def far_month(self) -> FutureContract | None:
        """The farthest expiry futures contract."""
        if not self._contracts:
            return None
        return max(self._contracts, key=lambda c: c.expiry)

    def by_expiry(self, expiry: date) -> list[FutureContract]:
        """Contracts for a specific expiry."""
        return [c for c in self._contracts if c.expiry == expiry]

    def __repr__(self) -> str:
        return f"FutureChain({self._underlying.symbol}, {self.contract_count} contracts)"


__all__ = [
    "FutureChain",
    "FutureContract",
    "OptionChain",
    "OptionContract",
]

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
from typing import TYPE_CHECKING, Any

from brokers.domain.enums import AssetClass, OptionType, OrderType, ProductType
from brokers.domain.values import Greeks, Quote

if TYPE_CHECKING:
    from brokers.domain.historical import HistoricalSeries
    from brokers.domain.instrument import Instrument
    from brokers.domain.values import MarketDepth, OrderResponse, Subscription


@dataclass(frozen=True, slots=True)
class OptionContract:
    """A single option contract within a chain.

    Each contract holds a full :class:`Instrument` (with provider injected)
    enabling direct trading and market data access without a separate
    materialization step.

    Convenience methods (``buy()``, ``sell()``, ``quote()``) delegate to
    the underlying instrument.
    """

    instrument: Instrument
    strike: Decimal
    option_type: OptionType
    expiry: date
    ltp: Decimal | None = None
    oi: int | None = None
    volume: int | None = None
    iv: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    greeks: Greeks | None = None

    @property
    def symbol(self) -> str:
        """Convenience — delegate to instrument."""
        return self.instrument.symbol

    @property
    def is_call(self) -> bool:
        return self.option_type == OptionType.CALL

    @property
    def is_put(self) -> bool:
        return self.option_type == OptionType.PUT

    async def quote(self) -> Quote:
        """Fetch the latest quote via the underlying instrument."""
        return await self.instrument.quote()

    async def refresh_ltp(self) -> Decimal:
        """Fetch the latest LTP from the exchange."""
        return await self.instrument.ltp()

    async def depth(self) -> MarketDepth:
        """Fetch the order book depth."""
        return await self.instrument.depth()

    async def history(
        self,
        *,
        timeframe: str = "1D",
        bars: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> HistoricalSeries:
        """Fetch historical OHLCV bars."""
        return await self.instrument.history(
            timeframe=timeframe, bars=bars, from_date=from_date, to_date=to_date,
        )

    async def buy(
        self,
        quantity: int,
        *,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal | None = None,
        product_type: ProductType = ProductType.INTRADAY,
        account: Any | None = None,
    ) -> OrderResponse:
        """Place a buy order for this option contract.

        Delegates to the underlying instrument's ``buy()`` method.
        """
        return await self.instrument.buy(
            quantity,
            order_type=order_type,
            price=price,
            product_type=product_type,
            account=account,
        )

    async def sell(
        self,
        quantity: int,
        *,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal | None = None,
        product_type: ProductType = ProductType.INTRADAY,
        account: Any | None = None,
    ) -> OrderResponse:
        """Place a sell order for this option contract."""
        return await self.instrument.sell(
            quantity,
            order_type=order_type,
            price=price,
            product_type=product_type,
            account=account,
        )

    async def subscribe_quotes(
        self, on_tick: Any | None = None,
    ) -> Subscription:
        """Subscribe to real-time quote updates."""
        return await self.instrument.subscribe_quotes(on_tick=on_tick)

    async def subscribe_depth(
        self, on_depth: Any | None = None,
    ) -> Subscription:
        """Subscribe to real-time depth updates."""
        return await self.instrument.subscribe_depth(on_depth=on_depth)


class OptionChain:
    """Aggregate root for option chain data.

    Owns a collection of :class:`OptionContract` values organized by
    expiry and strike.  Provides filtering by moneyness.

    Every contract in the chain is a full :class:`Instrument` — no
    separate ``as_instrument()`` step is needed.
    """

    __slots__ = ("_contracts", "_expiries", "_spot", "_strikes", "_underlying")

    def __init__(
        self,
        underlying: Instrument,
        *,
        contracts: list[OptionContract],
        spot: Decimal | None = None,
    ) -> None:
        self._underlying = underlying
        self._contracts = contracts
        self._spot = spot
        self._strikes = sorted({c.strike for c in contracts})
        self._expiries = sorted({c.expiry for c in contracts})

    @property
    def underlying(self) -> Instrument:
        return self._underlying

    @property
    def spot(self) -> Decimal | None:
        return self._spot

    @property
    def strikes(self) -> list[Decimal]:
        return list(self._strikes)

    @property
    def expiries(self) -> list[date]:
        return list(self._expiries)

    @property
    def contracts(self) -> list[OptionContract]:
        return list(self._contracts)

    @property
    def contract_count(self) -> int:
        return len(self._contracts)

    def calls(self, expiry: date | None = None) -> list[OptionContract]:
        return [
            c for c in self._contracts
            if c.is_call and (expiry is None or c.expiry == expiry)
        ]

    def puts(self, expiry: date | None = None) -> list[OptionContract]:
        return [
            c for c in self._contracts
            if c.is_put and (expiry is None or c.expiry == expiry)
        ]

    def atm(self, spot: Decimal | None = None) -> OptionContract | None:
        s = spot or self._spot
        if s is None or not self._strikes:
            return None
        closest_strike = min(self._strikes, key=lambda k: abs(k - s))
        calls_at_strike = [c for c in self._contracts if c.strike == closest_strike and c.is_call]
        return calls_at_strike[0] if calls_at_strike else None

    def atm_call(self, spot: Decimal | None = None) -> OptionContract | None:
        s = spot or self._spot
        if s is None or not self._strikes:
            return None
        closest = min(self._strikes, key=lambda k: abs(k - s))
        calls = [c for c in self._contracts if c.strike == closest and c.is_call]
        return calls[0] if calls else None

    def atm_put(self, spot: Decimal | None = None) -> OptionContract | None:
        s = spot or self._spot
        if s is None or not self._strikes:
            return None
        closest = min(self._strikes, key=lambda k: abs(k - s))
        puts = [c for c in self._contracts if c.strike == closest and c.is_put]
        return puts[0] if puts else None

    def itm_calls(self, spot: Decimal | None = None) -> list[OptionContract]:
        s = spot or self._spot
        if s is None:
            return []
        return [c for c in self._contracts if c.is_call and c.strike < s]

    def itm_puts(self, spot: Decimal | None = None) -> list[OptionContract]:
        s = spot or self._spot
        if s is None:
            return []
        return [c for c in self._contracts if c.is_put and c.strike > s]

    def otm_calls(self, spot: Decimal | None = None) -> list[OptionContract]:
        s = spot or self._spot
        if s is None:
            return []
        return [c for c in self._contracts if c.is_call and c.strike > s]

    def otm_puts(self, spot: Decimal | None = None) -> list[OptionContract]:
        s = spot or self._spot
        if s is None:
            return []
        return [c for c in self._contracts if c.is_put and c.strike < s]

    def total_call_oi(self, expiry: date | None = None) -> int:
        return sum(c.oi or 0 for c in self.calls(expiry))

    def total_put_oi(self, expiry: date | None = None) -> int:
        return sum(c.oi or 0 for c in self.puts(expiry))

    def pcr(self, expiry: date | None = None) -> Decimal | None:
        call_oi = self.total_call_oi(expiry)
        if call_oi == 0:
            return None
        put_oi = self.total_put_oi(expiry)
        return Decimal(str(put_oi)) / Decimal(str(call_oi))

    def __repr__(self) -> str:
        return f"OptionChain({self._underlying.symbol}, {self.contract_count} contracts)"


@dataclass(frozen=True, slots=True)
class FutureContract:
    """Single futures contract within a chain.

    Holds a full :class:`Instrument` with provider injected, enabling
    direct trading on chain members.
    """

    instrument: Instrument
    expiry: date
    lot_size: int = 1
    ltp: Decimal | None = None
    oi: int | None = None
    underlying: str = ""

    @property
    def symbol(self) -> str:
        return self.instrument.symbol

    async def buy(
        self,
        quantity: int,
        *,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal | None = None,
        product_type: ProductType = ProductType.INTRADAY,
        account: Any | None = None,
    ) -> OrderResponse:
        return await self.instrument.buy(
            quantity,
            order_type=order_type,
            price=price,
            product_type=product_type,
            account=account,
        )

    async def sell(
        self,
        quantity: int,
        *,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal | None = None,
        product_type: ProductType = ProductType.INTRADAY,
        account: Any | None = None,
    ) -> OrderResponse:
        return await self.instrument.sell(
            quantity,
            order_type=order_type,
            price=price,
            product_type=product_type,
            account=account,
        )


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
        if not self._contracts:
            return None
        return min(self._contracts, key=lambda c: c.expiry)

    def far_month(self) -> FutureContract | None:
        if not self._contracts:
            return None
        return max(self._contracts, key=lambda c: c.expiry)

    def by_expiry(self, expiry: date) -> list[FutureContract]:
        return [c for c in self._contracts if c.expiry == expiry]

    def __repr__(self) -> str:
        return f"FutureChain({self._underlying.symbol}, {self.contract_count} contracts)"


__all__ = [
    "FutureChain",
    "FutureContract",
    "OptionChain",
    "OptionContract",
]

"""Instrument — the rich aggregate root for market data.

Instrument owns its identity, cached market data state, active subscriptions,
and trading operations.  It delegates IO to an injected
:class:`MarketDataProvider`.

This is NOT an anemic data bag.  It has real behavior:
  - Caches the last quote/depth (memoization)
  - Tracks active subscriptions (state management)
  - Validates derivative properties (is_option, is_expired)
  - Delegates trading to Account (convenience, not ownership)

Thread safety: internal state protected by a lock.  Identity is immutable.

Created by a :class:`Platform` (factory) which injects the provider.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from brokers.domain.capabilities import Capability
from brokers.domain.enums import AssetClass, Exchange, OptionType, OrderType, ProductType, Side
from brokers.domain.values import MarketDepth, Quote, Subscription

if TYPE_CHECKING:
    from brokers.domain.account import Account
    from brokers.domain.capabilities import ProviderCapabilities
    from brokers.domain.historical import HistoricalSeries
    from brokers.domain.option_chain import FutureChain, OptionChain
    from brokers.domain.values import OrderResponse
    from brokers.provider.extensions import ExtensionAccess
    from brokers.provider.protocol import MarketDataProvider, Provider

# Domain-local default tick size (kept in the domain layer to avoid an
# infra→domain import; domain must not depend on brokers.constants).
DEFAULT_TICK_SIZE: Decimal = Decimal("0.05")


# ── Identity value (immutable, hashable) ───────────────────────────────────


@dataclass(frozen=True, slots=True)
class InstrumentIdentity:
    """Immutable identity for an instrument — the hashable core.

    Two instruments with the same identity are the same instrument.
    """

    symbol: str
    exchange: Exchange
    asset_class: AssetClass = AssetClass.EQUITY
    lot_size: int = 1
    tick_size: Decimal = DEFAULT_TICK_SIZE
    isin: str = ""
    trading_symbol: str = ""
    security_id: str = ""
    expiry: date | None = None
    strike: Decimal | None = None
    option_type: OptionType | None = None


# ── Rich Instrument aggregate root ─────────────────────────────────────────


class Instrument:
    """Rich domain object — the primary aggregate root for market data.

    Owns its state and behavior.  Delegates IO to an injected Provider.

    Usage::

        broker = Broker.dhan(client_id="123", access_token="tok")
        reliance = broker.instrument("RELIANCE", Exchange.NSE)
        quote = await reliance.quote()
        response = await reliance.buy(quantity=10)

    Thread safety: internal state protected by a lock.  Identity is immutable.
    """

    __slots__ = (
        "_cached_depth",
        "_cached_quote",
        "_identity",
        "_lock",
        "_provider",
        "_subscriptions",
    )

    def __init__(
        self,
        symbol: str,
        exchange: Exchange,
        asset_class: AssetClass = AssetClass.EQUITY,
        *,
        provider: Provider,
        lot_size: int = 1,
        tick_size: Decimal = DEFAULT_TICK_SIZE,
        isin: str = "",
        trading_symbol: str = "",
        security_id: str = "",
        expiry: date | None = None,
        strike: Decimal | None = None,
        option_type: OptionType | None = None,
    ) -> None:
        self._identity = InstrumentIdentity(
            symbol=symbol,
            exchange=exchange,
            asset_class=asset_class,
            lot_size=lot_size,
            tick_size=tick_size,
            isin=isin,
            trading_symbol=trading_symbol or symbol,
            security_id=security_id,
            expiry=expiry,
            strike=strike,
            option_type=option_type,
        )
        self._provider: Provider = provider
        self._lock = threading.RLock()
        self._cached_quote: Quote | None = None
        self._cached_depth: MarketDepth | None = None
        self._subscriptions: list[Subscription] = []

    # ── Identity (immutable, delegates to InstrumentIdentity) ────────

    @property
    def identity(self) -> InstrumentIdentity:
        return self._identity

    @property
    def symbol(self) -> str:
        return self._identity.symbol

    @property
    def exchange(self) -> Exchange:
        return self._identity.exchange

    @property
    def asset_class(self) -> AssetClass:
        return self._identity.asset_class

    @property
    def lot_size(self) -> int:
        return self._identity.lot_size

    @property
    def tick_size(self) -> Decimal:
        return self._identity.tick_size

    @property
    def isin(self) -> str:
        return self._identity.isin

    @property
    def trading_symbol(self) -> str:
        return self._identity.trading_symbol

    @property
    def security_id(self) -> str:
        return self._identity.security_id

    @property
    def expiry(self) -> date | None:
        return self._identity.expiry

    @property
    def strike(self) -> Decimal | None:
        return self._identity.strike

    @property
    def option_type(self) -> OptionType | None:
        return self._identity.option_type

    # ── Computed properties (pure, no IO) ────────────────────────────

    @property
    def is_derivative(self) -> bool:
        """True if this is a future or option."""
        return self._identity.asset_class in (AssetClass.FUTURE, AssetClass.OPTION)

    @property
    def is_option(self) -> bool:
        return self._identity.asset_class == AssetClass.OPTION

    @property
    def is_future(self) -> bool:
        return self._identity.asset_class == AssetClass.FUTURE

    @property
    def is_expired(self) -> bool:
        """True if the expiry date has passed (for derivatives)."""
        return self._identity.expiry is not None and self._identity.expiry < date.today()

    @property
    def is_equity(self) -> bool:
        return self._identity.asset_class == AssetClass.EQUITY

    @property
    def is_index(self) -> bool:
        return self._identity.asset_class == AssetClass.INDEX

    @property
    def key(self) -> str:
        """Canonical lookup key: ``"SYMBOL:EXCHANGE"``."""
        return f"{self._identity.symbol}:{self._identity.exchange.value}"

    def __hash__(self) -> int:
        return hash(self._identity)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Instrument):
            return NotImplemented
        return self._identity == other._identity

    def __repr__(self) -> str:
        return f"Instrument({self.key}, {self._identity.asset_class.value})"

    # ── Provider access ──────────────────────────────────────────────

    @property
    def provider(self) -> Provider:
        return self._provider

    @property
    def provider_capabilities(self) -> ProviderCapabilities:
        return self._provider.capabilities

    # ── Market data (delegates to provider, caches result) ───────────

    async def quote(self) -> Quote:
        """Fetch and cache the latest quote."""
        q = await self._provider.get_quote(self)
        with self._lock:
            self._cached_quote = q
        return q

    async def ltp(self) -> Decimal:
        """Fetch the last traded price."""
        return await self._provider.get_ltp(self)

    async def depth(self) -> MarketDepth:
        """Fetch and cache order book depth."""
        d = await self._provider.get_depth(self)
        with self._lock:
            self._cached_depth = d
        return d

    @property
    def cached_quote(self) -> Quote | None:
        """Last cached quote. No IO."""
        with self._lock:
            return self._cached_quote

    @property
    def cached_depth(self) -> MarketDepth | None:
        """Last cached depth. No IO."""
        with self._lock:
            return self._cached_depth

    async def history(
        self,
        *,
        timeframe: str = "1D",
        bars: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> HistoricalSeries:
        """Fetch historical OHLCV bars."""
        return await self._provider.get_history(
            self,
            timeframe=timeframe,
            bars=bars,
            from_date=from_date,
            to_date=to_date,
        )

    # ── Streaming (delegates to provider, tracks subscriptions) ──────

    async def subscribe_quotes(
        self, on_tick: Callable[[Quote], None] | None = None
    ) -> Subscription:
        """Subscribe to real-time quote updates."""
        if not self._provider.capabilities.supports(Capability.STREAMING):
            raise TypeError(
                f"Provider {self._provider.broker_id!r} does not support streaming."
            )
        sub = await self._provider.subscribe_quotes([self], on_tick=on_tick)
        with self._lock:
            self._subscriptions.append(sub)
        return sub

    async def subscribe_depth(
        self, on_depth: Callable[[MarketDepth], None] | None = None
    ) -> Subscription:
        """Subscribe to real-time depth updates."""
        if not self._provider.capabilities.supports(Capability.STREAMING):
            raise TypeError(
                f"Provider {self._provider.broker_id!r} does not support streaming."
            )
        sub = await self._provider.subscribe_depth([self], on_depth=on_depth)
        with self._lock:
            self._subscriptions.append(sub)
        return sub

    async def unsubscribe(self, subscription: Subscription) -> None:
        """Cancel an active subscription."""
        if not self._provider.capabilities.supports(Capability.STREAMING):
            raise TypeError(
                f"Provider {self._provider.broker_id!r} does not support streaming."
            )
        await self._provider.unsubscribe(subscription)
        with self._lock:
            if subscription in self._subscriptions:
                self._subscriptions.remove(subscription)

    async def unsubscribe_all(self) -> None:
        """Cancel all subscriptions for this instrument."""
        with self._lock:
            subs = list(self._subscriptions)
            self._subscriptions.clear()
        if self._provider.capabilities.supports(Capability.STREAMING):
            for sub in subs:
                await self._provider.unsubscribe(sub)

    @property
    def active_subscriptions(self) -> list[Subscription]:
        """List of active subscriptions (copy)."""
        with self._lock:
            return [s for s in self._subscriptions if s.is_active]

    # ── Trading (creates orders via Account) ─────────────────────────

    async def buy(
        self,
        quantity: int,
        *,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal | None = None,
        product_type: ProductType = ProductType.INTRADAY,
        account: Account | None = None,
    ) -> OrderResponse:
        """Place a buy order. Delegates to Account for risk gating."""
        from brokers.domain.requests import OrderRequest

        if account is None:
            if not self._provider.capabilities.supports(Capability.ORDER_PLACEMENT):
                raise TypeError(
                    f"Provider {self._provider.broker_id!r} does not support "
                    f"execution. Pass an explicit Account or use a full-service broker."
                )
            account = self._provider.default_account
        return await account.place_order(
            OrderRequest(
                instrument=self,
                symbol=self._identity.symbol,
                exchange=self._identity.exchange,
                side=Side.BUY,
                quantity=quantity,
                order_type=order_type,
                price=price or Decimal("0"),
                product_type=product_type,
            )
        )

    async def sell(
        self,
        quantity: int,
        *,
        order_type: OrderType = OrderType.MARKET,
        price: Decimal | None = None,
        product_type: ProductType = ProductType.INTRADAY,
        account: Account | None = None,
    ) -> OrderResponse:
        """Place a sell order. Delegates to Account for risk gating."""
        from brokers.domain.requests import OrderRequest

        if account is None:
            if not self._provider.capabilities.supports(Capability.ORDER_PLACEMENT):
                raise TypeError(
                    f"Provider {self._provider.broker_id!r} does not support "
                    f"execution. Pass an explicit Account or use a full-service broker."
                )
            account = self._provider.default_account
        return await account.place_order(
            OrderRequest(
                instrument=self,
                symbol=self._identity.symbol,
                exchange=self._identity.exchange,
                side=Side.SELL,
                quantity=quantity,
                order_type=order_type,
                price=price or Decimal("0"),
                product_type=product_type,
            )
        )

    # ── Derivatives ──────────────────────────────────────────────────

    async def option_chain(self, expiry: date | None = None) -> OptionChain:
        """Fetch the option chain (if this instrument is an underlying)."""
        return await self._provider.get_option_chain(self, expiry=expiry)

    async def future_chain(self) -> FutureChain:
        """Fetch the futures chain."""
        return await self._provider.get_future_chain(self)

    # ── Extensions (typed, capability-gated) ─────────────────────────

    @property
    def extensions(self) -> ExtensionAccess:
        """Typed access to broker-specific extensions."""
        return self._provider.extensions.for_instrument(self)

    # ── Lifecycle ────────────────────────────────────────────────────

    async def close(self) -> None:
        """Clean up: unsubscribe all streams."""
        await self.unsubscribe_all()


__all__ = ["Instrument", "InstrumentIdentity"]

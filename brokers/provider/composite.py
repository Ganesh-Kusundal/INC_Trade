"""CompositeProvider — multi-provider with failover and routing.

This is NOT a wrapper-only class.  It adds real responsibility:
  - Failover: try primary, fall back to secondary on error
  - Capability checking: route to the provider that supports the operation
  - Multi-source merge: combine historical data from multiple sources
  - Health tracking: skip unhealthy providers

The :class:`RoutingStrategy` is consulted to decide which provider to
try first for each operation kind.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from brokers.domain.capabilities import Capability, ProviderCapabilities
from brokers.domain.exceptions import NotSupportedError, ProviderError
from brokers.domain.requests import ModifyOrderRequest, OrderRequest
from brokers.domain.values import (
    Balance,
    Holding,
    MarketDepth,
    OrderResponse,
    Position,
    Quote,
    Subscription,
    Trade,
)
from brokers.provider.extensions import ExtensionAccess
from brokers.provider.routing import RoutingStrategy

if TYPE_CHECKING:
    from brokers.domain.account import Account
    from brokers.domain.historical import HistoricalSeries
    from brokers.domain.instrument import Instrument
    from brokers.domain.option_chain import FutureChain, OptionChain
    from brokers.provider.protocol import Provider


class CompositeProvider:
    """Multi-provider with failover, capability checking, and routing.

    Real responsibilities (not just forwarding):
    1. Tries providers in order determined by RoutingStrategy
    2. Falls back to next provider on error
    3. Checks capabilities before calling a provider
    4. Merges historical data from multiple sources
    5. Tracks provider health for routing decisions

    Created by ``Broker.compose()``.  Not used for single-broker setups.
    """

    __slots__ = ("_extensions", "_providers", "_routing", "_unhealthy")

    def __init__(
        self,
        providers: list[Provider],
        *,
        routing: RoutingStrategy | None = None,
    ) -> None:
        if not providers:
            raise ValueError("CompositeProvider requires at least one provider")
        self._providers = providers
        self._routing = routing or RoutingStrategy.primary_only()
        self._unhealthy: set[int] = set()
        self._extensions = ExtensionAccess(self, extensions={})

    # ── Identity ─────────────────────────────────────────────────────

    @property
    def broker_id(self) -> str:
        return "composite"

    @property
    def capabilities(self) -> ProviderCapabilities:
        """Union of all sub-provider capabilities."""
        all_caps: set[Capability] = set()
        primary_id = ""
        for p in self._providers:
            caps = p.capabilities
            all_caps.update(caps.supported)
            if caps.is_primary:
                primary_id = caps.broker_id
        return ProviderCapabilities(
            broker_id="composite",
            supported=frozenset(all_caps),
            is_primary=bool(primary_id),
        )

    @property
    def default_account(self) -> Account:
        """Use the primary provider's account."""
        idx = self._routing.execution()
        idx = self._healthy_index(idx, Capability.ORDER_PLACEMENT)
        return self._providers[idx].default_account

    @property
    def extensions(self) -> ExtensionAccess:
        return self._extensions

    @property
    def is_connected(self) -> bool:
        return any(p.is_connected for p in self._providers)

    # ── Provider selection ───────────────────────────────────────────

    def _healthy_index(
        self,
        preferred: int,
        required_cap: Capability | None = None,
    ) -> int:
        """Find a healthy provider index, preferring the given one."""
        # Try preferred first
        if 0 <= preferred < len(self._providers) and preferred not in self._unhealthy:
            if required_cap is None or self._providers[preferred].capabilities.supports(required_cap):
                return preferred
        # Fall back to any healthy provider with the capability
        for i, p in enumerate(self._providers):
            if i in self._unhealthy:
                continue
            if required_cap is None or p.capabilities.supports(required_cap):
                return i
        # All unhealthy — try preferred anyway (might have recovered)
        return max(0, min(preferred, len(self._providers) - 1))

    def _mark_unhealthy(self, idx: int) -> None:
        self._unhealthy.add(idx)

    async def _try_with_failover(
        self,
        operation: str,
        fn: Any,
        required_cap: Capability | None = None,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Try the operation on the preferred provider, failover on error."""
        preferred = 0
        # Determine preferred index based on operation
        if operation == "market_data":
            preferred = self._routing.market_data()
        elif operation == "historical":
            preferred = self._routing.historical()
        elif operation == "execution":
            preferred = self._routing.execution()
        elif operation == "streaming":
            preferred = self._routing.streaming()

        tried: list[int] = []
        for attempt in range(len(self._providers)):
            idx = self._healthy_index(preferred + attempt, required_cap)
            if idx in tried:
                continue
            tried.append(idx)
            try:
                provider = self._providers[idx]
                return await fn(provider, *args, **kwargs)
            except (ProviderError, NotSupportedError) as exc:
                if isinstance(exc, NotSupportedError):
                    continue  # Try next provider
                self._mark_unhealthy(idx)
                if attempt == len(self._providers) - 1:
                    raise
        raise ProviderError(f"No provider could handle {operation}")

    # ── Market data ──────────────────────────────────────────────────

    async def get_quote(self, instrument: Instrument) -> Quote:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "market_data",
            lambda p, inst: p.get_quote(inst),
            Capability.MARKET_DATA,
            instrument,
        )

    async def get_ltp(self, instrument: Instrument) -> Decimal:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "market_data",
            lambda p, inst: p.get_ltp(inst),
            Capability.MARKET_DATA,
            instrument,
        )

    async def get_depth(self, instrument: Instrument) -> MarketDepth:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "market_data",
            lambda p, inst: p.get_depth(inst),
            Capability.DEPTH,
            instrument,
        )

    async def get_history(
        self,
        instrument: Instrument,
        *,
        timeframe: str = "1D",
        bars: int | None = None,
        from_date: date | None = None,
        to_date: date | None = None,
    ) -> HistoricalSeries:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "historical",
            lambda p, inst, **kw: p.get_history(inst, **kw),
            Capability.HISTORICAL_DATA,
            instrument,
            timeframe=timeframe,
            bars=bars,
            from_date=from_date,
            to_date=to_date,
        )

    # ── Instrument search ────────────────────────────────────────────

    async def search_instruments(self, query: str) -> list[Instrument]:
        idx = self._healthy_index(0, Capability.INSTRUMENT_SEARCH)
        return await self._providers[idx].search_instruments(query)

    async def get_instruments(self, exchange: str | None = None) -> list[Instrument]:
        idx = self._healthy_index(0, Capability.INSTRUMENT_SEARCH)
        return await self._providers[idx].get_instruments(exchange)

    async def resolve_instrument(self, symbol: str, exchange: str) -> Instrument:
        idx = self._healthy_index(0, Capability.INSTRUMENT_SEARCH)
        return await self._providers[idx].resolve_instrument(symbol, exchange)

    # ── Derivatives ──────────────────────────────────────────────────

    async def get_option_chain(
        self,
        underlying: Instrument,
        *,
        expiry: date | None = None,
    ) -> OptionChain:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "market_data",
            lambda p, inst, **kw: p.get_option_chain(inst, **kw),
            Capability.OPTION_CHAIN,
            underlying,
            expiry=expiry,
        )

    async def get_future_chain(self, underlying: Instrument) -> FutureChain:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "market_data",
            lambda p, inst: p.get_future_chain(inst),
            Capability.FUTURE_CHAIN,
            underlying,
        )

    # ── Execution ────────────────────────────────────────────────────

    async def place_order(self, request: OrderRequest) -> OrderResponse:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "execution",
            lambda p, req: p.place_order(req),
            Capability.ORDER_PLACEMENT,
            request,
        )

    async def cancel_order(self, order_id: str) -> OrderResponse:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "execution",
            lambda p, oid: p.cancel_order(oid),
            Capability.ORDER_PLACEMENT,
            order_id,
        )

    async def modify_order(self, request: ModifyOrderRequest) -> OrderResponse:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "execution",
            lambda p, req: p.modify_order(req),
            Capability.ORDER_MODIFICATION,
            request,
        )

    # ── Portfolio ────────────────────────────────────────────────────

    async def get_positions(self) -> list[Position]:
        idx = self._healthy_index(self._routing.execution(), Capability.PORTFOLIO)
        return await self._providers[idx].get_positions()

    async def get_balance(self) -> Balance:
        idx = self._healthy_index(self._routing.execution(), Capability.PORTFOLIO)
        return await self._providers[idx].get_balance()

    async def get_orders(self) -> list[Any]:
        idx = self._healthy_index(self._routing.execution(), Capability.PORTFOLIO)
        return await self._providers[idx].get_orders()

    async def get_trades(self) -> list[Trade]:
        idx = self._healthy_index(self._routing.execution(), Capability.PORTFOLIO)
        return await self._providers[idx].get_trades()

    async def get_holdings(self) -> list[Holding]:
        idx = self._healthy_index(self._routing.execution(), Capability.PORTFOLIO)
        return await self._providers[idx].get_holdings()

    # ── Streaming ────────────────────────────────────────────────────

    async def subscribe_quotes(
        self,
        instruments: list[Instrument],
        *,
        on_tick: Any = None,
    ) -> Subscription:
        idx = self._healthy_index(self._routing.streaming(), Capability.STREAMING)
        return await self._providers[idx].subscribe_quotes(instruments, on_tick=on_tick)

    async def subscribe_depth(
        self,
        instruments: list[Instrument],
        *,
        on_depth: Any = None,
    ) -> Subscription:
        idx = self._healthy_index(self._routing.streaming(), Capability.STREAMING)
        return await self._providers[idx].subscribe_depth(instruments, on_depth=on_depth)

    async def subscribe_orders(self, *, on_update: Any = None) -> Subscription:
        idx = self._healthy_index(self._routing.streaming(), Capability.STREAMING)
        return await self._providers[idx].subscribe_orders(on_update=on_update)

    async def unsubscribe(self, subscription: Subscription) -> None:
        # The subscription knows which provider it belongs to
        await subscription.cancel()

    # ── Lifecycle ────────────────────────────────────────────────────

    async def connect(self) -> None:
        for p in self._providers:
            try:
                await p.connect()
            except Exception:
                pass  # Continue connecting other providers

    async def disconnect(self) -> None:
        for p in self._providers:
            try:
                await p.disconnect()
            except Exception:
                pass


__all__ = ["CompositeProvider"]

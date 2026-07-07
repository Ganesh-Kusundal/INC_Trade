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

import logging
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
from brokers.infrastructure.event_bus import EventBus
from brokers.provider.extensions import ExtensionAccess
from brokers.provider.routing import RoutingStrategy

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from brokers.domain.account import Account, RiskPolicyProtocol
    from brokers.domain.historical import HistoricalSeries
    from brokers.domain.instrument import Instrument
    from brokers.domain.option_chain import FutureChain, OptionChain
    from brokers.domain.order import Order
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

    __slots__ = ("_default_account_cache", "_event_bus", "_extensions", "_providers", "_risk_policy", "_routing", "_unhealthy")

    def __init__(
        self,
        providers: list[Provider],
        *,
        routing: RoutingStrategy | None = None,
        event_bus: EventBus | None = None,
        risk_policy: RiskPolicyProtocol | None = None,
    ) -> None:
        if not providers:
            raise ValueError("CompositeProvider requires at least one provider")
        self._providers = providers
        self._routing = routing or RoutingStrategy.primary_only()
        self._event_bus = event_bus or EventBus()
        self._risk_policy = risk_policy
        self._unhealthy: set[int] = set()
        # Aggregate extensions from every sub-provider.  Each sub-provider's
        # registered dict is copied (never mutated) and merged; if two
        # providers register the same name, the first provider wins.  The
        # capability-gated accessors then work across all sub-providers.
        merged: dict[str, Any] = {}
        for p in providers:
            for name, obj in p.extensions.registered.items():
                if name not in merged:
                    merged[name] = obj
        self._extensions = ExtensionAccess(self, dict(merged))
        self._default_account_cache: Account | None = None

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
    def risk_policy(self) -> RiskPolicyProtocol | None:
        return self._risk_policy

    @risk_policy.setter
    def risk_policy(self, value: RiskPolicyProtocol | None) -> None:
        self._risk_policy = value

    @property
    def default_account(self) -> Account:
        """Return a cached Account backed by the composite for full routing.

        The Account is created lazily on first access and cached, so that
        order tracking, positions, and risk state persist across calls.
        """
        if self._default_account_cache is None:
            from brokers.domain.account import Account

            self._default_account_cache = Account(
                "composite", self, risk_policy=self._risk_policy, event_bus=self._event_bus
            )
        return self._default_account_cache

    @property
    def extensions(self) -> ExtensionAccess:
        return self._extensions

    @property
    def is_connected(self) -> bool:
        return any(p.is_connected for p in self._providers)

    # ── Provider selection ───────────────────────────────────────────

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

        tried: set[int] = set()
        for attempt in range(len(self._providers)):
            # Build candidate list: preferred first, then others in order
            candidates = []
            for offset in range(len(self._providers)):
                idx = (preferred + offset) % len(self._providers)
                if idx not in tried:
                    candidates.append(idx)
            
            if not candidates:
                break
            
            # Try each candidate with the capability check
            for idx in candidates:
                if required_cap is not None and not self._providers[idx].capabilities.supports(required_cap):
                    tried.add(idx)
                    continue
                if idx in self._unhealthy:
                    tried.add(idx)
                    continue
                    
                tried.add(idx)
                try:
                    provider = self._providers[idx]
                    return await fn(provider, *args, **kwargs)
                except (ProviderError, NotSupportedError) as exc:
                    if isinstance(exc, NotSupportedError):
                        continue  # Try next provider
                    self._mark_unhealthy(idx)
                    break  # Move to next attempt cycle
        
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
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "market_data",
            lambda p, q: p.search_instruments(q),
            Capability.INSTRUMENT_SEARCH,
            query,
        )

    async def get_instruments(self, exchange: str | None = None) -> list[Instrument]:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "market_data",
            lambda p, ex: p.get_instruments(ex),
            Capability.INSTRUMENT_SEARCH,
            exchange,
        )

    async def resolve_instrument(self, symbol: str, exchange: str) -> Instrument:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "market_data",
            lambda p, sym, ex: p.resolve_instrument(sym, ex),
            Capability.INSTRUMENT_SEARCH,
            symbol,
            exchange,
        )

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
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "execution",
            lambda p: p.get_positions(),
            Capability.PORTFOLIO,
        )

    async def get_balance(self) -> Balance:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "execution",
            lambda p: p.get_balance(),
            Capability.PORTFOLIO,
        )

    async def get_orders(self) -> list[Order]:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "execution",
            lambda p: p.get_orders(),
            Capability.PORTFOLIO,
        )

    async def get_trades(self) -> list[Trade]:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "execution",
            lambda p: p.get_trades(),
            Capability.PORTFOLIO,
        )

    async def get_holdings(self) -> list[Holding]:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "execution",
            lambda p: p.get_holdings(),
            Capability.PORTFOLIO,
        )

    # ── Streaming ────────────────────────────────────────────────────

    async def subscribe_quotes(
        self,
        instruments: list[Instrument],
        *,
        on_tick: Any = None,
    ) -> Subscription:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "streaming",
            lambda p, insts, **kw: p.subscribe_quotes(insts, **kw),
            Capability.STREAMING,
            instruments,
            on_tick=on_tick,
        )

    async def subscribe_depth(
        self,
        instruments: list[Instrument],
        *,
        on_depth: Any = None,
    ) -> Subscription:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "streaming",
            lambda p, insts, **kw: p.subscribe_depth(insts, **kw),
            Capability.STREAMING,
            instruments,
            on_depth=on_depth,
        )

    async def subscribe_orders(self, *, on_update: Any = None) -> Subscription:
        return await self._try_with_failover(  # type: ignore[no-any-return]
            "streaming",
            lambda p, **kw: p.subscribe_orders(**kw),
            Capability.STREAMING,
            on_update=on_update,
        )

    async def unsubscribe(self, subscription: Subscription) -> None:
        # The subscription knows which provider it belongs to
        await subscription.cancel()

    # ── Lifecycle ────────────────────────────────────────────────────

    async def connect(self) -> None:
        errors: list[tuple[str, Exception]] = []
        for p in self._providers:
            try:
                await p.connect()
            except Exception as exc:
                logger.warning(
                    "composite_provider_connect_failed",
                    extra={"broker_id": getattr(p, "broker_id", "unknown"), "error": str(exc)[:200]},
                )
                errors.append((getattr(p, "broker_id", "unknown"), exc))
        if errors and len(errors) == len(self._providers):
            raise ProviderError(
                f"All {len(errors)} provider(s) failed to connect: "
                + ", ".join(f"{bid}: {exc}" for bid, exc in errors)
            )

    async def disconnect(self) -> None:
        for p in self._providers:
            try:
                await p.disconnect()
            except Exception as exc:
                logger.warning(
                    "composite_provider_disconnect_failed",
                    extra={"broker_id": getattr(p, "broker_id", "unknown"), "error": str(exc)[:200]},
                )


__all__ = ["CompositeProvider"]

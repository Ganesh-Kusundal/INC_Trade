"""Broker — deprecated alias for :class:`Platform`.

Kept for backward compatibility.  All ``Broker`` usage is forwarded
to :class:`Platform`.  New code should use ``Platform`` directly.

Usage (deprecated)::

    broker = Broker.dhan(client_id="123", access_token="tok")

Usage (recommended)::

    platform = await Platform.connect("dhan")
    reliance = platform.instrument("NSE:RELIANCE")
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

from brokers.domain.account import Account
from brokers.domain.capabilities import ProviderCapabilities
from brokers.domain.enums import AssetClass, Exchange
from brokers.domain.instrument import Instrument
from brokers.risk import RiskPolicy

if TYPE_CHECKING:
    from brokers.common.instrument_resolver import InstrumentResolver
    from brokers.infrastructure.event_bus import EventBus
    from brokers.provider.protocol import Provider
    from brokers.provider.routing import RoutingStrategy


class Broker:
    """Factory and DI entry point.

    Holds a provider and creates Instruments and Accounts with that
    provider injected.  This is NOT a wrapper — it's a factory that
    wires dependencies at creation time.

    Created via static methods:
      - ``Broker.dhan(...)`` — Dhan provider
      - ``Broker.upstox(...)`` — Upstox provider
      - ``Broker.paper()`` — Paper trading provider
      - ``Broker.compose(...)`` — Multi-broker with routing
    """

    __slots__ = ("_account", "_event_bus", "_provider", "_risk_policy")

    def __init__(
        self,
        provider: Provider,
        *,
        risk_policy: RiskPolicy | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        warnings.warn(
            "Broker is deprecated — use Platform instead",
            DeprecationWarning,
            stacklevel=2,
        )
        self._provider = provider
        self._risk_policy = risk_policy
        self._event_bus = event_bus
        self._account: Account | None = None

    # ── Factory methods ──────────────────────────────────────────────

    @staticmethod
    def dhan(
        *,
        client_id: str,
        access_token: str,
        risk_policy: RiskPolicy | None = None,
        event_bus: EventBus | None = None,
        resolver: InstrumentResolver | None = None,
        **kwargs: Any,
    ) -> Broker:
        """Create a Broker backed by the Dhan provider."""
        from brokers.dhan.dhan_provider import DhanProvider

        provider = DhanProvider(
            client_id=client_id,
            access_token=access_token,
            resolver=resolver,
            **kwargs,
        )
        return Broker(provider, risk_policy=risk_policy, event_bus=event_bus)

    @staticmethod
    def upstox(
        *,
        access_token: str,
        risk_policy: RiskPolicy | None = None,
        event_bus: EventBus | None = None,
        resolver: InstrumentResolver | None = None,
        **kwargs: Any,
    ) -> Broker:
        """Create a Broker backed by the Upstox provider."""
        from brokers.upstox.upstox_provider import UpstoxProvider

        provider = UpstoxProvider(
            access_token=access_token,
            resolver=resolver,
            **kwargs,
        )
        return Broker(provider, risk_policy=risk_policy, event_bus=event_bus)

    @staticmethod
    def paper(
        *,
        initial_balance: Any = None,
        risk_policy: RiskPolicy | None = None,
        event_bus: EventBus | None = None,
        **kwargs: Any,
    ) -> Broker:
        """Create a Broker backed by the in-memory paper trading provider."""
        from brokers.paper.paper_provider import PaperProvider

        provider = PaperProvider(
            initial_balance=initial_balance,
            **kwargs,
        )
        return Broker(provider, risk_policy=risk_policy, event_bus=event_bus)

    @staticmethod
    def compose(
        *,
        primary: Broker,
        secondary: Broker,
        routing: RoutingStrategy | None = None,
        risk_policy: RiskPolicy | None = None,
        event_bus: EventBus | None = None,
    ) -> Broker:
        """Create a multi-broker Broker with failover and routing."""
        from brokers.provider.composite import CompositeProvider
        from brokers.provider.routing import RoutingStrategy as RS

        providers = [primary._provider, secondary._provider]
        composite = CompositeProvider(providers, routing=routing or RS.primary_only())
        return Broker(
            composite,
            risk_policy=risk_policy or primary._risk_policy,
            event_bus=event_bus or primary._event_bus,
        )

    # ── Public API ───────────────────────────────────────────────────

    def instrument(
        self,
        symbol: str,
        exchange: Exchange,
        *,
        asset_class: AssetClass = AssetClass.EQUITY,
        **kwargs: Any,
    ) -> Instrument:
        """Create a rich Instrument with the provider injected.

        This is the primary entry point for market data access.
        The returned Instrument owns its state and delegates IO to
        the provider.
        """
        return Instrument(
            symbol=symbol,
            exchange=exchange,
            asset_class=asset_class,
            provider=self._provider,
            **kwargs,
        )

    def account(self) -> Account:
        """Get the Account for this broker.

        The Account is lazily created with the risk policy injected.
        Risk gating happens inside ``Account.place_order()`` — not in
        a wrapper.
        """
        if self._account is None:
            self._account = Account(
                account_id=f"{self._provider.broker_id}_default",
                provider=self._provider,
                risk_policy=self._risk_policy,
                event_bus=self._event_bus,
            )
        return self._account

    # ── Properties ───────────────────────────────────────────────────

    @property
    def provider(self) -> Provider:
        return self._provider

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._provider.capabilities

    @property
    def broker_id(self) -> str:
        return self._provider.broker_id

    @property
    def is_connected(self) -> bool:
        return self._provider.is_connected

    # ── Lifecycle ────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Connect the provider (HTTP session, WebSocket, auth)."""
        await self._provider.connect()

    async def disconnect(self) -> None:
        """Disconnect the provider."""
        await self._provider.disconnect()

    def __repr__(self) -> str:
        return f"Broker({self._provider.broker_id})"


__all__ = ["Broker"]

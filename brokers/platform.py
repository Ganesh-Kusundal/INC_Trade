"""Platform — composition root and orchestration entry point.

Replaces ``Broker`` as the SDK's primary entry point.  Platform wires
authentication, provider creation, and domain object injection.  It is
*not* a thin wrapper — it's a complete Broker Platform that hides every
broker implementation detail.

Usage::

    # Auto-login (recommended) — zero credentials in code
    platform = await Platform.connect("dhan")
    reliance = platform.instrument("NSE:RELIANCE")
    quote = await reliance.quote()

    # Manual token (advanced users)
    platform = Platform.dhan(client_id="123", access_token="tok")
    reliance = platform.instrument("RELIANCE", Exchange.NSE)

    # Paper trading
    platform = Platform.paper()

    # Multi-broker with routing
    platform = Platform.compose(
        primary=await Platform.connect("dhan"),
        secondary=Platform.upstox(access_token="tok2"),
    )
"""

from __future__ import annotations

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


class Platform:
    """Composition root and DI entry point.

    Wires authentication, provider creation, and domain object injection.
    Created via:

        - ``Platform.connect("dhan")`` — auto-login (recommended)
        - ``Platform.connect("upstox")`` — auto-login
        - ``Platform.dhan(...)`` — Dhan with manual token
        - ``Platform.upstox(...)`` — Upstox with manual token
        - ``Platform.paper()`` — Paper trading provider
        - ``Platform.compose(...)`` — Multi-broker with routing

    Holds a provider and creates Instruments and Accounts with that
    provider injected.  Auto-detects which interfaces the provider
    supports — a data-only provider won't expose an Account.
    """

    __slots__ = ("_account", "_event_bus", "_provider", "_risk_policy", "_token_scheduler")

    def __init__(
        self,
        provider: Provider,
        *,
        risk_policy: RiskPolicy | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        self._provider = provider
        self._risk_policy = risk_policy
        self._event_bus = event_bus
        self._account: Account | None = None
        self._token_scheduler: Any = None  # Set by connect(); stopped in disconnect()

    # ── Auto-login (recommended) ───────────────────────────────────────

    @staticmethod
    async def connect(provider_name: str, **kwargs: Any) -> Platform:
        """Auto-login and connect to a broker.

        Reads credentials from environment variables / .env files and
        performs the full login flow automatically.  No tokens or
        client IDs appear in application code.

        Args:
            provider_name: ``"dhan"``, ``"upstox"``, or ``"paper"``.

        Returns:
            A fully connected :class:`Platform`.

        Raises:
            ValueError: If the provider is unknown or credentials are missing.
            DhanTotpError: If TOTP login fails.
            TotpRateLimitError: If TOTP cooldown is active.
        """
        if provider_name == "dhan":
            return await Platform._connect_dhan(**kwargs)
        if provider_name == "upstox":
            return await Platform._connect_upstox(**kwargs)
        if provider_name == "paper":
            return Platform.paper(**kwargs)
        raise ValueError(
            f"Unknown provider: {provider_name!r}. "
            f"Use 'dhan', 'upstox', or 'paper'."
        )

    @staticmethod
    async def _connect_dhan(**kwargs: Any) -> Platform:
        """Auto-login to Dhan via TOTP.

        Flow:
        1. CredentialResolver loads .env.dhan
        2. AuthManager loads cached token or TOTP-login for a fresh one
        3. DhanProvider created with the acquired token
        4. DhanTokenScheduler starts background refresh daemon
        5. Token receiver hooks scheduler → provider hot-swap
        6. Platform wraps provider + scheduler for lifecycle management
        """
        from pathlib import Path

        from brokers.common.auth.credential_resolver import CredentialResolver
        from brokers.common.auth.token_manager import AuthManager, JsonTokenStateStore
        from brokers.dhan.dhan_provider import DhanProvider
        from brokers.dhan.token_scheduler import DhanTokenScheduler
        from brokers.dhan.totp_client import DhanTotpClient

        creds = CredentialResolver.for_dhan()

        # ── Fast path: static access token already in env ─────────
        if creds.access_token:
            provider = DhanProvider(
                client_id=creds.client_id,
                access_token=creds.access_token,
                resolver=kwargs.pop("resolver", None),
                **kwargs,
            )
            return Platform(provider)

        # ── TOTP auto-login path ─────────────────────────────────
        if not creds.has_totp:
            raise ValueError(
                "DHAN_TOTP_SECRET + DHAN_PIN are required for auto-login. "
                "Set them in .env.dhan or provide DHAN_ACCESS_TOKEN."
            )

        # 1. Persistent token cache (survives process restarts)
        store = JsonTokenStateStore(
            Path.home() / ".config" / "inc_trade" / ".dhan_token.json"
        )

        # 2. TOTP client with cooldown guard
        totp_client = DhanTotpClient()

        # 3. Auth manager — orchestrates acquire / refresh / cache
        auth_manager = AuthManager(
            on_acquire=lambda: totp_client.login(
                creds.totp_secret, creds.pin, creds.client_id
            ),
            on_refresh=lambda old: totp_client.refresh(
                creds.totp_secret, creds.pin, creds.client_id
            ),
            store=store,
            refresh_buffer_seconds=300,
            broker_name="dhan",
        )

        # 4. Acquire a token (load from cache or TOTP-login)
        try:
            auth_manager.ensure_valid()
        except Exception as exc:
            raise ValueError(
                f"Dhan auto-login failed: {exc}. "
                f"Check DHAN_CLIENT_ID, DHAN_TOTP_SECRET, DHAN_PIN "
                f"in .env.dhan"
            ) from exc

        # 5. Create provider with the fresh token
        provider = DhanProvider(
            client_id=creds.client_id,
            access_token=auth_manager.access_token,
            resolver=kwargs.pop("resolver", None),
            **kwargs,
        )

        # 6. Background daemon keeps the token alive
        scheduler = DhanTokenScheduler(auth_manager)
        scheduler.start()

        # 7. Hot-swap hook — when scheduler refreshes, update the client
        auth_manager.register_token_receiver(
            lambda new_token: provider.update_token(new_token)
        )

        # 8. Build platform with scheduler for lifecycle management
        platform = Platform(provider)
        platform._token_scheduler = scheduler
        return platform

    @staticmethod
    async def _connect_upstox(**kwargs: Any) -> Platform:
        """Auto-login to Upstox.

        Currently supports static access tokens.  TOTP-based auto-login
        will be added when the Upstox TOTP client is implemented.
        """
        from brokers.common.auth.credential_resolver import CredentialResolver
        from brokers.upstox.upstox_provider import UpstoxProvider

        creds = CredentialResolver.for_upstox()

        # ── Fast path: static access token ───────────────────────
        if creds.access_token:
            provider = UpstoxProvider(
                access_token=creds.access_token,
                client_id=creds.client_id,
                api_key=creds.api_key,
                api_secret=creds.api_secret,
                **kwargs,
            )
            return Platform(provider)

        # ── TOTP path: not yet implemented (Upstox TOTP client needed)
        if creds.has_totp:
            raise NotImplementedError(
                "Upstox TOTP auto-login is not yet implemented. "
                "Use Platform.upstox(access_token=...) or set "
                "UPSTOX_ACCESS_TOKEN in .env.upstox."
            )

        raise ValueError(
            "UPSTOX_ACCESS_TOKEN or (UPSTOX_TOTP_SECRET + UPSTOX_PIN + "
            "UPSTOX_MOBILE) must be set in .env.upstox."
        )

    # ── Factory methods (manual token, advanced users) ─────────────────

    @staticmethod
    def dhan(
        *,
        client_id: str,
        access_token: str,
        risk_policy: RiskPolicy | None = None,
        event_bus: EventBus | None = None,
        resolver: InstrumentResolver | None = None,
        **kwargs: Any,
    ) -> Platform:
        """Create a Platform backed by the Dhan provider."""
        from brokers.dhan.dhan_provider import DhanProvider

        provider = DhanProvider(
            client_id=client_id,
            access_token=access_token,
            resolver=resolver,
            **kwargs,
        )
        return Platform(provider, risk_policy=risk_policy, event_bus=event_bus)

    @staticmethod
    def upstox(
        *,
        access_token: str,
        risk_policy: RiskPolicy | None = None,
        event_bus: EventBus | None = None,
        resolver: InstrumentResolver | None = None,
        **kwargs: Any,
    ) -> Platform:
        """Create a Platform backed by the Upstox provider."""
        from brokers.upstox.upstox_provider import UpstoxProvider

        provider = UpstoxProvider(
            access_token=access_token,
            resolver=resolver,
            **kwargs,
        )
        return Platform(provider, risk_policy=risk_policy, event_bus=event_bus)

    @staticmethod
    def paper(
        *,
        initial_balance: Any = None,
        risk_policy: RiskPolicy | None = None,
        event_bus: EventBus | None = None,
        **kwargs: Any,
    ) -> Platform:
        """Create a Platform backed by the in-memory paper trading provider."""
        from brokers.paper.paper_provider import PaperProvider

        provider = PaperProvider(
            initial_balance=initial_balance,
            **kwargs,
        )
        return Platform(provider, risk_policy=risk_policy, event_bus=event_bus)

    @staticmethod
    def compose(
        *,
        primary: Platform,
        secondary: Platform,
        routing: RoutingStrategy | None = None,
        risk_policy: RiskPolicy | None = None,
        event_bus: EventBus | None = None,
    ) -> Platform:
        """Create a multi-broker Platform with failover and routing."""
        from brokers.provider.composite import CompositeProvider
        from brokers.provider.routing import RoutingStrategy as RS

        providers = [primary._provider, secondary._provider]
        composite = CompositeProvider(providers, routing=routing or RS.primary_only())
        return Platform(
            composite,
            risk_policy=risk_policy or primary._risk_policy,
            event_bus=event_bus or primary._event_bus,
        )

    # ── Public API ───────────────────────────────────────────────────────

    def instrument(
        self,
        symbol_or_key: str,
        exchange: Exchange | None = None,
        *,
        asset_class: AssetClass = AssetClass.EQUITY,
        **kwargs: Any,
    ) -> Instrument:
        """Create a rich Instrument with the provider injected.

        Supports two formats::

            # Colon format (new, recommended)
            platform.instrument("NSE:RELIANCE")

            # Two-argument format (original, still works)
            platform.instrument("RELIANCE", Exchange.NSE)

        This is the primary entry point for market data access.
        The returned Instrument owns its state and delegates IO to
        the provider.
        """
        if exchange is None:
            if ":" not in symbol_or_key:
                raise ValueError(
                    f"Cannot parse {symbol_or_key!r}: "
                    f"provide an exchange or use 'EXCHANGE:SYMBOL' format "
                    f"(e.g. 'NSE:RELIANCE')"
                )
            exchange_str, symbol = symbol_or_key.split(":", 1)
            exchange = Exchange(exchange_str)
        else:
            symbol = symbol_or_key

        return Instrument(
            symbol=symbol,
            exchange=exchange,
            asset_class=asset_class,
            provider=self._provider,
            **kwargs,
        )

    def account(self) -> Account:
        """Get the Account for this platform.

        The Account is lazily created with the risk policy injected.
        Risk gating happens inside ``Account.place_order()`` — not in
        a wrapper.

        Raises:
            TypeError: If this platform's provider does not support
                execution (e.g. a data-only provider).
        """
        from brokers.provider.protocol import ExecutionProvider

        if not isinstance(self._provider, ExecutionProvider):
            raise TypeError(
                f"Provider {self._provider.broker_id!r} does not support "
                f"execution.  Use a full-service broker or paper trading."
            )
        if self._account is None:
            self._account = Account(
                account_id=f"{self._provider.broker_id}_default",
                provider=self._provider,
                risk_policy=self._risk_policy,
                event_bus=self._event_bus,
            )
        return self._account

    # ── Properties ───────────────────────────────────────────────────────

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

    # ── Lifecycle ────────────────────────────────────────────────────────

    async def open(self) -> None:
        """Open the provider connection (HTTP session, WebSocket, auth).

        For auto-login users (``Platform.connect("dhan")``), the connection
        is already established.  This is for manual-token users::

            platform = Platform.dhan(client_id="123", access_token="tok")
            await platform.open()
        """
        await self._provider.connect()

    async def disconnect(self) -> None:
        """Disconnect: stop token scheduler (if any), then provider."""
        if self._token_scheduler is not None:
            self._token_scheduler.stop()
            self._token_scheduler = None
        await self._provider.disconnect()

    def __repr__(self) -> str:
        return f"Platform({self._provider.broker_id})"


__all__ = ["Platform"]

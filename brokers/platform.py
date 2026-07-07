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

import base64
import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from brokers.domain.account import Account
from brokers.domain.capabilities import Capability, ProviderCapabilities
from brokers.domain.enums import AssetClass, Exchange
from brokers.domain.instrument import Instrument
from brokers.infrastructure.event_bus import EventBus
from brokers.risk import RiskPolicy

if TYPE_CHECKING:
    from brokers.common.auth.token_manager import AuthManager
    from brokers.common.instrument_resolver import InstrumentResolver
    from brokers.provider.protocol import Provider
    from brokers.provider.routing import RoutingStrategy

logger = logging.getLogger(__name__)


def _set_risk_policy(provider: Provider, risk_policy: RiskPolicy | None) -> None:
    """Best-effort propagation of the risk policy into a provider.

    Providers expose a settable ``risk_policy`` attribute; setting it makes
    ``provider.default_account`` return a risk-gated Account.  If the provider
    lacks the attribute (data-only providers), we silently skip — they don't
    support execution anyway.
    """
    if risk_policy is None:
        return
    if hasattr(type(provider), "risk_policy"):
        try:
            provider.risk_policy = risk_policy  # type: ignore[attr-defined]
        except (AttributeError, TypeError):
            pass


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
        self._event_bus = event_bus or EventBus()
        self._account: Account | None = None
        self._token_scheduler: Any = None  # Set by connect(); stopped in disconnect()
        # Propagate the risk policy into the provider so that
        # ``provider.default_account`` (used by Instrument.buy()/sell())
        # builds an Account that is risk-gated.  Providers expose a
        # settable ``risk_policy`` attribute (no-op if absent).
        _set_risk_policy(provider, risk_policy)

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
        4. BackgroundTokenScheduler starts background refresh daemon
        5. Token receiver hooks scheduler → provider hot-swap
        6. Platform wraps provider + scheduler for lifecycle management
        """
        from brokers.common.auth.credential_resolver import CredentialResolver
        from brokers.common.auth.token_manager import AuthManager, JsonTokenStateStore
        from brokers.dhan.dhan_provider import DhanProvider
        from brokers.dhan.totp_client import DhanTotpClient, DhanTotpError, TotpRateLimitError

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

        totp_client = DhanTotpClient()
        store = JsonTokenStateStore(
            Path.home() / ".config" / "inc_trade" / ".dhan_token.json"
        )
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

        def _provider_factory(token: str) -> DhanProvider:
            return DhanProvider(
                client_id=creds.client_id,
                access_token=token,
                resolver=kwargs.pop("resolver", None),
                **kwargs,
            )

        return Platform._build_with_auth(
            auth_manager=auth_manager,
            provider_factory=_provider_factory,
            broker_name="dhan",
            error_types=(DhanTotpError, TotpRateLimitError),
            error_hint="Check DHAN_CLIENT_ID, DHAN_TOTP_SECRET, DHAN_PIN in .env.dhan",
        )

    @staticmethod
    async def _connect_upstox(**kwargs: Any) -> Platform:
        """Auto-login to Upstox via headless TOTP or static token.

        Flow:
        1. CredentialResolver loads .env.local
        2. If static access token is valid → create provider directly
        3. If session credentials → UpstoxOAuthClient.login() (headless TOTP)
           (6-step automated flow: dialog → OTP → TOTP → PIN → OAuth → token)
        4. Background refresh daemon keeps token alive
        """
        from brokers.common.auth.credential_resolver import CredentialResolver
        from brokers.common.auth.token_manager import AuthManager, JsonTokenStateStore
        from brokers.upstox.totp_client import UpstoxOAuthClient, UpstoxTotpError
        from brokers.upstox.upstox_provider import UpstoxProvider

        creds = CredentialResolver.for_upstox()

        # ── Fast path: static access token (only if not expired) ──
        if creds.access_token and Platform._is_jwt_valid(creds.access_token):
            provider = UpstoxProvider(
                access_token=creds.access_token,
                **kwargs,
            )
            return Platform(provider)

        if creds.access_token:
            logger.info("upstox_static_token_expired_falling_through_to_oauth")

        # ── OAuth authorization code flow ─────────────────────────
        if not creds.has_oauth:
            raise ValueError(
                "UPSTOX_ACCESS_TOKEN (valid) or "
                "(UPSTOX_API_KEY + UPSTOX_API_SECRET + UPSTOX_REDIRECT_URI) "
                "must be set in .env.local"
            )

        oauth_client = UpstoxOAuthClient(
            api_key=creds.api_key,
            api_secret=creds.api_secret,
            redirect_uri=creds.redirect_uri,
            username=creds.username,
            password=creds.password,
            pin=creds.pin,
            totp_secret=creds.totp_secret,
        )
        store = JsonTokenStateStore(
            Path.home() / ".config" / "inc_trade" / ".upstox_token.json"
        )
        auth_manager = AuthManager(
            on_acquire=oauth_client.login,
            on_refresh=lambda old: oauth_client.refresh(),
            store=store,
            refresh_buffer_seconds=300,
            broker_name="upstox",
        )

        def _provider_factory(token: str) -> UpstoxProvider:
            return UpstoxProvider(access_token=token, **kwargs)

        return Platform._build_with_auth(
            auth_manager=auth_manager,
            provider_factory=_provider_factory,
            broker_name="upstox",
            error_types=(UpstoxTotpError,),
            error_hint=(
                "Check UPSTOX_API_KEY, UPSTOX_API_SECRET, UPSTOX_REDIRECT_URI "
                "in .env.local"
            ),
        )

    @staticmethod
    def _is_jwt_valid(token: str) -> bool:
        """Decode a JWT payload and check whether it is still valid.

        Returns ``False`` if the token is malformed, has no ``exp`` claim,
        or has already expired.  No signature verification is performed —
        this is a client-side sanity check only.
        """
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return False
            payload = parts[1]
            # Add padding
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            decoded = base64.urlsafe_b64decode(payload)
            data = json.loads(decoded)
            exp = data.get("exp", 0)
            return time.time() < exp
        except Exception:
            return False

    @staticmethod
    def _build_with_auth(
        *,
        auth_manager: AuthManager,
        provider_factory: Callable[[str], Provider],
        broker_name: str,
        error_types: tuple[type[Exception], ...] = (),
        error_hint: str = "",
    ) -> Platform:
        """Shared auth → provider → scheduler wiring.

        1. Acquire a token (load from cache or TOTP-login)
        2. Create provider with the fresh token
        3. Start background token-refresh daemon
        4. Hook scheduler → provider hot-swap
        5. Return Platform with scheduler for lifecycle management
        """
        from brokers.common.auth.token_scheduler import BackgroundTokenScheduler

        try:
            auth_manager.ensure_valid()
        except Exception as exc:
            if error_types and isinstance(exc, error_types):
                raise  # Let broker-specific errors propagate
            raise ValueError(
                f"{broker_name.capitalize()} auto-login failed: {exc}. {error_hint}"
            ) from exc

        provider = provider_factory(auth_manager.access_token)

        scheduler = BackgroundTokenScheduler(auth_manager)
        scheduler.start()

        auth_manager.register_token_receiver(
            lambda new_token: provider.update_token(new_token)
        )

        platform = Platform(provider)
        platform._token_scheduler = scheduler
        return platform

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
        composite = CompositeProvider(
            providers,
            routing=routing or RS.primary_only(),
            event_bus=event_bus or primary._event_bus,
        )
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
        if not self._provider.capabilities.supports(Capability.ORDER_PLACEMENT):
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

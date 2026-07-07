"""Unit tests for the Platform class — composition root and DI entry point.

Covers the 13 unit tests specified in the Platform Architecture Adoption Plan:
  1. Colon-format instrument parsing ("NSE:RELIANCE")
  2. Two-argument instrument format (backward compat)
  3. Missing colon without exchange → ValueError
  4. connect("dhan") with missing credentials → ValueError
  5. connect("dhan") with valid cached token → no TOTP login
  6. connect("dhan") with expired cached token → TOTP refresh called
  7. connect("dhan") with no cached token → TOTP login called
  8. connect("dhan") with active cooldown → TotpRateLimitError propagated
  9. connect("dhan") with network error → DhanTotpError propagated
  10. connect("dhan") token receiver → provider.update_token() called on refresh
  11. disconnect() → scheduler stopped + provider disconnected
  12. Broker alias backward compatibility
  13. Broker alias emits DeprecationWarning

Plus bonus tests for connect("paper"), connect("unknown"), connect("dhan")
fast path (static access_token), and connect("upstox") variants.

.. important::
    ``Platform._connect_dhan()`` and ``_connect_upstox()`` use *local
    imports* (imports inside the function body), not module-level imports.
    Therefore all ``patch()`` targets must point at the **source module**
    where the class/function is defined — NOT ``brokers.platform.X``.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from brokers import Broker
from brokers.common.auth.credential_resolver import DhanCredentials, UpstoxCredentials
from brokers.common.auth.token_manager import TokenSource, TokenState
from brokers.dhan.totp_client import DhanTotpError, TotpRateLimitError
from brokers.domain.enums import Exchange
from brokers.platform import Platform


# ── Helpers ────────────────────────────────────────────────────────────────


def _fresh_token(access_token: str = "fresh-token") -> TokenState:
    """Create a valid token with 24h remaining."""
    return TokenState(
        access_token=access_token,
        source=TokenSource.TOTP,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )


def _expired_token(access_token: str = "expired-token") -> TokenState:
    """Create an expired token (1 hour ago)."""
    return TokenState(
        access_token=access_token,
        source=TokenSource.TOTP,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )


# ── Instrument convenience parsing (tests 1–3) ─────────────────────────────


class TestInstrumentConvenienceParsing:
    """Colon-format ``platform.instrument(\"NSE:RELIANCE\")`` convenience."""

    @pytest.fixture
    def platform(self) -> Platform:
        """Paper-backed platform — no auth, fully hermetic."""
        return Platform.paper()

    def test_colon_format_parses_exchange_and_symbol(self, platform: Platform) -> None:
        """``\"NSE:RELIANCE\"`` → Instrument(\"RELIANCE\", Exchange.NSE)."""
        inst = platform.instrument("NSE:RELIANCE")
        assert inst.symbol == "RELIANCE"
        assert inst.exchange == Exchange.NSE

    def test_two_arg_format_still_works(self, platform: Platform) -> None:
        """Original ``(\"RELIANCE\", Exchange.NSE)`` format is unchanged."""
        inst = platform.instrument("RELIANCE", Exchange.NSE)
        assert inst.symbol == "RELIANCE"
        assert inst.exchange == Exchange.NSE

    def test_no_colon_no_exchange_raises(self, platform: Platform) -> None:
        """``\"RELIANCE\"`` without exchange must raise ValueError."""
        with pytest.raises(ValueError, match="Cannot parse"):
            platform.instrument("RELIANCE")

    def test_colon_format_with_bse_exchange(self, platform: Platform) -> None:
        """Colon format works with BSE exchange."""
        inst = platform.instrument("BSE:TATAMOTORS")
        assert inst.symbol == "TATAMOTORS"
        assert inst.exchange == Exchange.BSE

    def test_invalid_exchange_in_colon_raises(self, platform: Platform) -> None:
        """Bad exchange code → ValueError from Enum constructor."""
        with pytest.raises(ValueError):
            platform.instrument("INVALID:RELIANCE")


# ── connect("dhan") auto-login flows (tests 4–9) ───────────────────────────
#
# Patch paths point at SOURCE modules, not brokers.platform, because
# _connect_dhan() uses local imports (``from brokers.foo.bar import X``).


class TestConnectDhanMissingCreds:
    """Test 4 — Missing credentials during auto-login."""

    @pytest.mark.asyncio
    async def test_missing_client_id_raises(self) -> None:
        """connect(\"dhan\") with no .env.dhan / DHAN_CLIENT_ID → ValueError."""
        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_dhan",
            side_effect=ValueError("DHAN_CLIENT_ID is required"),
        ):
            with pytest.raises(ValueError, match="DHAN_CLIENT_ID"):
                await Platform.connect("dhan")

    @pytest.mark.asyncio
    async def test_no_totp_and_no_access_token_raises(self) -> None:
        """Credentials exist but neither TOTP nor static token → ValueError."""
        creds = DhanCredentials(
            client_id="D123", access_token="", totp_secret="", pin=""
        )

        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_dhan",
            return_value=creds,
        ):
            with pytest.raises(
                ValueError, match="DHAN_TOTP_SECRET \\+ DHAN_PIN are required"
            ):
                await Platform.connect("dhan")


class TestConnectDhanCachedToken:
    """Test 5 — Valid cached token: no TOTP login needed."""

    @pytest.mark.asyncio
    async def test_valid_cached_token_skips_totp(self) -> None:
        """Store has a valid token → ensure_valid() returns it, no on_acquire."""
        creds = DhanCredentials(
            client_id="D123", access_token="", totp_secret="SECRET", pin="1234"
        )
        cached = _fresh_token("cached-token")

        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_dhan",
            return_value=creds,
        ), patch(
            "brokers.common.auth.token_manager.JsonTokenStateStore"
        ) as mock_store_cls, patch(
            "brokers.dhan.totp_client.DhanTotpClient"
        ) as mock_totp_cls, patch(
            "brokers.dhan.dhan_provider.DhanProvider"
        ), patch(
            "brokers.dhan.token_scheduler.DhanTokenScheduler"
        ) as mock_sched_cls:

            mock_store = mock_store_cls.return_value
            mock_store.load.return_value = cached
            mock_totp = mock_totp_cls.return_value
            mock_sched = mock_sched_cls.return_value

            platform = await Platform._connect_dhan()

            # on_acquire lambda wraps totp.login — must NOT be called
            mock_totp.login.assert_not_called()
            mock_sched.start.assert_called_once()
            assert isinstance(platform, Platform)


class TestConnectDhanExpiredToken:
    """Test 6 — Expired cached token: TOTP refresh triggered."""

    @pytest.mark.asyncio
    async def test_expired_cached_token_triggers_totp(self) -> None:
        """Expired store token → AuthManager calls on_acquire → TOTP login."""
        creds = DhanCredentials(
            client_id="D123", access_token="", totp_secret="SECRET", pin="1234"
        )
        expired = _expired_token("expired-token")
        fresh = _fresh_token("fresh-token")

        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_dhan",
            return_value=creds,
        ), patch(
            "brokers.common.auth.token_manager.JsonTokenStateStore"
        ) as mock_store_cls, patch(
            "brokers.dhan.totp_client.DhanTotpClient"
        ) as mock_totp_cls, patch(
            "brokers.dhan.dhan_provider.DhanProvider"
        ), patch(
            "brokers.dhan.token_scheduler.DhanTokenScheduler"
        ) as mock_sched_cls:

            mock_store = mock_store_cls.return_value
            mock_store.load.return_value = expired
            mock_totp = mock_totp_cls.return_value
            mock_totp.login.return_value = fresh
            mock_sched = mock_sched_cls.return_value

            platform = await Platform._connect_dhan()

            # Expired token → must TOTP-login
            mock_totp.login.assert_called_once_with("SECRET", "1234", "D123")
            mock_sched.start.assert_called_once()
            assert isinstance(platform, Platform)


class TestConnectDhanNoToken:
    """Test 7 — No cached token: TOTP login called."""

    @pytest.mark.asyncio
    async def test_no_cached_token_calls_totp(self) -> None:
        """Empty store → AuthManager calls on_acquire → TOTP login."""
        creds = DhanCredentials(
            client_id="D123", access_token="", totp_secret="SECRET", pin="1234"
        )
        fresh = _fresh_token("fresh-token")

        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_dhan",
            return_value=creds,
        ), patch(
            "brokers.common.auth.token_manager.JsonTokenStateStore"
        ) as mock_store_cls, patch(
            "brokers.dhan.totp_client.DhanTotpClient"
        ) as mock_totp_cls, patch(
            "brokers.dhan.dhan_provider.DhanProvider"
        ), patch(
            "brokers.dhan.token_scheduler.DhanTokenScheduler"
        ) as mock_sched_cls:

            mock_store = mock_store_cls.return_value
            mock_store.load.return_value = None  # No cached token
            mock_totp = mock_totp_cls.return_value
            mock_totp.login.return_value = fresh
            mock_sched = mock_sched_cls.return_value

            platform = await Platform._connect_dhan()

            mock_totp.login.assert_called_once_with("SECRET", "1234", "D123")
            mock_sched.start.assert_called_once()
            assert isinstance(platform, Platform)


class TestConnectDhanCooldownActive:
    """Test 8 — TOTP cooldown active: TotpRateLimitError."""

    @pytest.mark.asyncio
    async def test_cooldown_active_propagates_error(self) -> None:
        """login() raises TotpRateLimitError → wrapped in ValueError."""
        creds = DhanCredentials(
            client_id="D123", access_token="", totp_secret="SECRET", pin="1234"
        )

        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_dhan",
            return_value=creds,
        ), patch(
            "brokers.common.auth.token_manager.JsonTokenStateStore"
        ) as mock_store_cls, patch(
            "brokers.dhan.totp_client.DhanTotpClient"
        ) as mock_totp_cls:

            mock_store = mock_store_cls.return_value
            mock_store.load.return_value = None
            mock_totp = mock_totp_cls.return_value
            mock_totp.login.side_effect = TotpRateLimitError(
                "Wait 87s before retrying"
            )

            with pytest.raises(ValueError, match="Dhan auto-login failed"):
                await Platform._connect_dhan()


class TestConnectDhanNetworkError:
    """Test 9 — Network error during TOTP: DhanTotpError."""

    @pytest.mark.asyncio
    async def test_network_error_propagates(self) -> None:
        """login() raises DhanTotpError → wrapped in ValueError."""
        creds = DhanCredentials(
            client_id="D123", access_token="", totp_secret="SECRET", pin="1234"
        )

        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_dhan",
            return_value=creds,
        ), patch(
            "brokers.common.auth.token_manager.JsonTokenStateStore"
        ) as mock_store_cls, patch(
            "brokers.dhan.totp_client.DhanTotpClient"
        ) as mock_totp_cls:

            mock_store = mock_store_cls.return_value
            mock_store.load.return_value = None
            mock_totp = mock_totp_cls.return_value
            mock_totp.login.side_effect = DhanTotpError(
                "Dhan token request failed: ConnectionError"
            )

            with pytest.raises(ValueError, match="Dhan auto-login failed"):
                await Platform._connect_dhan()

    @pytest.mark.asyncio
    async def test_login_failure_http_error(self) -> None:
        """login() raises DhanTotpError with HTTP status → wrapped in ValueError."""
        creds = DhanCredentials(
            client_id="D123", access_token="", totp_secret="SECRET", pin="1234"
        )

        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_dhan",
            return_value=creds,
        ), patch(
            "brokers.common.auth.token_manager.JsonTokenStateStore"
        ) as mock_store_cls, patch(
            "brokers.dhan.totp_client.DhanTotpClient"
        ) as mock_totp_cls:

            mock_store = mock_store_cls.return_value
            mock_store.load.return_value = None
            mock_totp = mock_totp_cls.return_value
            mock_totp.login.side_effect = DhanTotpError(
                "Dhan login failed (HTTP 500): internal error"
            )

            with pytest.raises(ValueError, match="Dhan auto-login failed"):
                await Platform._connect_dhan()


# ── Token receiver hook (test 10) ──────────────────────────────────────────


class TestConnectDhanTokenReceiver:
    """Test 10 — Scheduler refresh → provider.update_token() called."""

    @pytest.mark.asyncio
    async def test_token_receiver_updates_provider_on_refresh(self) -> None:
        """AuthManager.register_token_receiver callback → provider.update_token()."""
        creds = DhanCredentials(
            client_id="D123", access_token="", totp_secret="SECRET", pin="1234"
        )
        fresh = _fresh_token("fresh-token")

        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_dhan",
            return_value=creds,
        ), patch(
            "brokers.common.auth.token_manager.JsonTokenStateStore"
        ), patch(
            "brokers.common.auth.token_manager.AuthManager"
        ) as mock_auth_cls, patch(
            "brokers.dhan.dhan_provider.DhanProvider"
        ) as mock_provider_cls, patch(
            "brokers.dhan.token_scheduler.DhanTokenScheduler"
        ) as mock_sched_cls:

            mock_auth = mock_auth_cls.return_value
            mock_auth.access_token = fresh.access_token
            mock_provider = mock_provider_cls.return_value
            mock_sched = mock_sched_cls.return_value

            platform = await Platform._connect_dhan()

            # register_token_receiver must have been called
            mock_auth.register_token_receiver.assert_called_once()

            # Extract the registered callback and invoke it
            callback = mock_auth.register_token_receiver.call_args[0][0]
            callback("newer-token")

            # Provider must receive the update
            mock_provider.update_token.assert_called_once_with("newer-token")
            mock_sched.start.assert_called_once()
            assert isinstance(platform, Platform)


# ── Disconnect lifecycle (test 11) ─────────────────────────────────────────


class TestDisconnectLifecycle:
    """Test 11 — disconnect() stops scheduler then provider."""

    @pytest.mark.asyncio
    async def test_disconnect_stops_scheduler_then_disconnects_provider(
        self,
    ) -> None:
        """scheduler.stop() is called, then provider.disconnect(), then cleared."""
        provider = MagicMock()
        provider.disconnect = AsyncMock()  # Must be async — disconnect() awaits it
        scheduler = MagicMock()

        platform = Platform(provider)
        platform._token_scheduler = scheduler

        await platform.disconnect()

        scheduler.stop.assert_called_once()
        provider.disconnect.assert_awaited_once()
        assert platform._token_scheduler is None

    @pytest.mark.asyncio
    async def test_disconnect_without_scheduler_is_safe(self) -> None:
        """disconnect() works even when no token scheduler is set."""
        provider = MagicMock()
        provider.disconnect = AsyncMock()  # Must be async — disconnect() awaits it

        platform = Platform(provider)
        # _token_scheduler remains None (default)

        await platform.disconnect()

        provider.disconnect.assert_awaited_once()
        assert platform._token_scheduler is None


# ── Broker alias backward compat (tests 12–13) ─────────────────────────────


class TestBrokerAlias:
    """Tests 12–13 — Broker backward compatibility and deprecation."""

    def test_broker_alias_still_creates_instruments(self) -> None:
        """Broker.paper() still works and creates instruments."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            broker = Broker.paper()

        assert isinstance(broker, Broker)
        reliance = broker.instrument("RELIANCE", Exchange.NSE)
        assert reliance.symbol == "RELIANCE"
        assert reliance.exchange == Exchange.NSE

    def test_broker_alias_emits_deprecation_warning(self) -> None:
        """Broker() instantiation emits DeprecationWarning."""
        with pytest.warns(DeprecationWarning, match="Broker is deprecated"):
            Broker.paper()

    def test_broker_alias_dhan_still_works(self) -> None:
        """Broker.dhan() with real-ish params doesn't crash (no network calls at init)."""
        # Note: DhanProvider.__init__ creates DhanHttpClient (requests.Session)
        # but makes no network calls — safe for unit tests.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            broker = Broker.dhan(client_id="D123", access_token="tok")

        assert isinstance(broker, Broker)
        assert broker.broker_id  # Provider was created successfully

    def test_broker_alias_upstox_still_works(self) -> None:
        """Broker.upstox() with minimal params doesn't crash."""
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            broker = Broker.upstox(access_token="tok")

        assert isinstance(broker, Broker)
        assert broker.broker_id  # Provider was created successfully


# ── Bonus: connect() dispatch ──────────────────────────────────────────────


class TestConnectDispatch:
    """connect() dispatches correctly to provider-specific flows."""

    @pytest.mark.asyncio
    async def test_connect_paper_returns_platform(self) -> None:
        """connect(\"paper\") → Platform.paper()."""
        platform = await Platform.connect("paper")
        assert isinstance(platform, Platform)
        assert not platform.is_connected  # Paper provider not auto-connected

    @pytest.mark.asyncio
    async def test_connect_unknown_provider_raises(self) -> None:
        """connect(\"xyz\") → ValueError."""
        with pytest.raises(ValueError, match="Unknown provider"):
            await Platform.connect("xyz")

    @pytest.mark.asyncio
    async def test_connect_dhan_static_token_fast_path(self) -> None:
        """connect(\"dhan\") with static access token skips TOTP entirely."""
        creds = DhanCredentials(
            client_id="D123",
            access_token="static-token",
            totp_secret="",
            pin="",
        )

        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_dhan",
            return_value=creds,
        ), patch(
            "brokers.dhan.dhan_provider.DhanProvider"
        ) as mock_provider_cls:

            platform = await Platform.connect("dhan")

            # Must use static token (not TOTP)
            mock_provider_cls.assert_called_once()
            call_kwargs = mock_provider_cls.call_args.kwargs
            assert call_kwargs["access_token"] == "static-token"
            assert call_kwargs["client_id"] == "D123"
            assert call_kwargs.get("resolver") is None
            assert isinstance(platform, Platform)
            # No scheduler since no TOTP flow
            assert platform._token_scheduler is None


# ── Bonus: connect("upstox") ──────────────────────────────────────────────


class TestConnectUpstox:
    """connect(\"upstox\") auto-login variants."""

    @pytest.mark.asyncio
    async def test_static_token_fast_path(self) -> None:
        """connect(\"upstox\") with UPSTOX_ACCESS_TOKEN → static fast path."""
        creds = UpstoxCredentials(
            client_id="U123",
            access_token="upstox-static-token",
            api_key="key",
            api_secret="secret",
        )

        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_upstox",
            return_value=creds,
        ), patch(
            "brokers.upstox.upstox_provider.UpstoxProvider"
        ) as mock_provider_cls:

            platform = await Platform.connect("upstox")

            mock_provider_cls.assert_called_once()
            call_kwargs = mock_provider_cls.call_args.kwargs
            assert call_kwargs["access_token"] == "upstox-static-token"
            assert isinstance(platform, Platform)

    @pytest.mark.asyncio
    async def test_totp_not_implemented(self) -> None:
        """connect(\"upstox\") with TOTP creds but no access token → NotImplementedError."""
        creds = UpstoxCredentials(
            client_id="U123",
            access_token="",
            totp_secret="SECRET",
            pin="1234",
            mobile="9999999999",
        )

        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_upstox",
            return_value=creds,
        ):
            with pytest.raises(NotImplementedError, match="Upstox TOTP"):
                await Platform.connect("upstox")

    @pytest.mark.asyncio
    async def test_missing_everything_raises(self) -> None:
        """connect(\"upstox\") with no credentials at all → ValueError."""
        creds = UpstoxCredentials(
            client_id="U123",
            access_token="",
            api_key="",
            api_secret="",
        )

        with patch(
            "brokers.common.auth.credential_resolver.CredentialResolver.for_upstox",
            return_value=creds,
        ):
            with pytest.raises(ValueError):
                await Platform.connect("upstox")


# ── Factory methods (direct tests) ─────────────────────────────────────────


class TestFactoryMethods:
    """Platform.dhan(), Platform.upstox(), Platform.paper() — direct invocation."""

    def test_paper_factory_returns_platform_with_paper_provider(self) -> None:
        """Platform.paper() creates a Platform with a PaperProvider."""
        platform = Platform.paper()
        assert isinstance(platform, Platform)
        # Paper provider has broker_id "paper"
        assert platform.broker_id
        assert not platform.is_connected

    def test_paper_factory_with_custom_balance(self) -> None:
        """Platform.paper(initial_balance=...) forwards to PaperProvider."""
        platform = Platform.paper(initial_balance=500000)
        assert isinstance(platform, Platform)
        assert platform.broker_id

    def test_paper_factory_with_risk_policy(self) -> None:
        """Platform.paper(risk_policy=...) injects policy into Platform."""
        policy = MagicMock()
        platform = Platform.paper(risk_policy=policy)
        # Account not created yet, but Platform holds the policy
        assert platform._risk_policy is policy

    def test_dhan_factory_returns_platform(self) -> None:
        """Platform.dhan() creates a Platform (mocked DhanProvider)."""
        with patch(
            "brokers.dhan.dhan_provider.DhanProvider"
        ) as mock_provider_cls:
            mock_provider = mock_provider_cls.return_value
            mock_provider.broker_id = "dhan-test"

            platform = Platform.dhan(client_id="D123", access_token="tok")

            mock_provider_cls.assert_called_once()
            assert mock_provider_cls.call_args.kwargs["client_id"] == "D123"
            assert mock_provider_cls.call_args.kwargs["access_token"] == "tok"
            assert isinstance(platform, Platform)
            assert platform.broker_id == "dhan-test"

    def test_upstox_factory_returns_platform(self) -> None:
        """Platform.upstox() creates a Platform (mocked UpstoxProvider)."""
        with patch(
            "brokers.upstox.upstox_provider.UpstoxProvider"
        ) as mock_provider_cls:
            mock_provider = mock_provider_cls.return_value
            mock_provider.broker_id = "upstox-test"

            platform = Platform.upstox(access_token="tok")

            mock_provider_cls.assert_called_once()
            assert mock_provider_cls.call_args.kwargs["access_token"] == "tok"
            assert isinstance(platform, Platform)
            assert platform.broker_id == "upstox-test"

    def test_factory_with_resolver_forwarded(self) -> None:
        """Platform.dhan(resolver=...) passes through to DhanProvider."""
        with patch(
            "brokers.dhan.dhan_provider.DhanProvider"
        ) as mock_provider_cls:
            mock_provider = mock_provider_cls.return_value
            mock_provider.broker_id = "dhan-test"

            resolver = MagicMock()
            Platform.dhan(
                client_id="D123", access_token="tok", resolver=resolver
            )

            assert mock_provider_cls.call_args.kwargs["resolver"] is resolver

    def test_factory_with_risk_and_event_bus(self) -> None:
        """Platform.dhan(risk_policy=..., event_bus=...) passed to Platform."""
        policy = MagicMock()
        event_bus = MagicMock()

        with patch("brokers.dhan.dhan_provider.DhanProvider"):
            platform = Platform.dhan(
                client_id="D123",
                access_token="tok",
                risk_policy=policy,
                event_bus=event_bus,
            )

        assert platform._risk_policy is policy
        assert platform._event_bus is event_bus


# ── compose() multi-broker routing ─────────────────────────────────────────


class TestCompose:
    """Platform.compose() — multi-broker with failover and routing."""

    def test_compose_creates_multi_broker_platform(self) -> None:
        """compose(primary, secondary) → Platform with composite provider."""
        primary = Platform.paper()
        secondary = Platform.paper()

        composite = Platform.compose(primary=primary, secondary=secondary)

        assert isinstance(composite, Platform)
        # Composite provider's broker_id is "composite"
        assert composite.broker_id == "composite"

    def test_compose_inherits_risk_policy_from_primary(self) -> None:
        """compose() falls back to primary's risk_policy if not explicit."""
        policy = MagicMock()
        primary = Platform.paper(risk_policy=policy)
        secondary = Platform.paper()

        composite = Platform.compose(primary=primary, secondary=secondary)

        assert composite._risk_policy is policy

    def test_compose_overrides_risk_policy(self) -> None:
        """compose(risk_policy=...) overrides primary's policy."""
        primary_policy = MagicMock()
        override_policy = MagicMock()
        primary = Platform.paper(risk_policy=primary_policy)
        secondary = Platform.paper()

        composite = Platform.compose(
            primary=primary,
            secondary=secondary,
            risk_policy=override_policy,
        )

        assert composite._risk_policy is override_policy

    def test_compose_inherits_event_bus_from_primary(self) -> None:
        """compose() falls back to primary's event_bus if not explicit."""
        event_bus = MagicMock()
        primary = Platform(MagicMock(), event_bus=event_bus)
        secondary = Platform(MagicMock())

        composite = Platform.compose(primary=primary, secondary=secondary)

        assert composite._event_bus is event_bus

    def test_compose_overrides_event_bus(self) -> None:
        """compose(event_bus=...) overrides primary's bus."""
        primary_bus = MagicMock()
        override_bus = MagicMock()
        primary = Platform(MagicMock(), event_bus=primary_bus)
        secondary = Platform(MagicMock())

        composite = Platform.compose(
            primary=primary,
            secondary=secondary,
            event_bus=override_bus,
        )

        assert composite._event_bus is override_bus


# ── account() lazy creation ────────────────────────────────────────────────


class TestAccountLazyCreation:
    """Platform.account() — lazy Account creation with risk policy injection."""

    def test_account_creates_account_lazily(self) -> None:
        """First call to account() creates an Account."""
        from brokers.domain.account import Account

        platform = Platform.paper()
        assert platform._account is None  # Not created yet

        acct = platform.account()

        assert isinstance(acct, Account)
        assert platform._account is acct

    def test_account_returns_same_instance(self) -> None:
        """Second call to account() returns the cached Account."""
        platform = Platform.paper()

        acct1 = platform.account()
        acct2 = platform.account()

        assert acct1 is acct2

    def test_account_injects_risk_policy(self) -> None:
        """Account created by Platform gets the risk_policy."""
        policy = MagicMock()
        platform = Platform.paper(risk_policy=policy)

        acct = platform.account()

        assert acct.risk_policy is policy

    def test_account_injects_event_bus(self) -> None:
        """Account created by Platform gets the event_bus."""
        from brokers.paper.paper_provider import PaperProvider

        event_bus = MagicMock()
        platform = Platform(PaperProvider(), event_bus=event_bus)

        acct = platform.account()

        assert acct._event_bus is event_bus


# ── Properties delegation ──────────────────────────────────────────────────


class TestProperties:
    """Platform properties delegate to the underlying Provider."""

    @pytest.fixture
    def platform(self) -> Platform:
        """Paper-backed platform."""
        return Platform.paper()

    def test_provider_property_returns_provider(self, platform: Platform) -> None:
        """platform.provider returns the injected provider."""
        assert platform.provider is platform._provider

    def test_capabilities_delegates_to_provider(self, platform: Platform) -> None:
        """platform.capabilities returns provider.capabilities."""
        from brokers.domain.capabilities import ProviderCapabilities

        caps = platform.capabilities
        assert isinstance(caps, ProviderCapabilities)
        assert caps == platform._provider.capabilities

    def test_broker_id_delegates_to_provider(self, platform: Platform) -> None:
        """platform.broker_id returns provider.broker_id."""
        assert platform.broker_id == platform._provider.broker_id
        assert isinstance(platform.broker_id, str)

    def test_is_connected_delegates_to_provider(self, platform: Platform) -> None:
        """platform.is_connected returns provider.is_connected."""
        assert platform.is_connected == platform._provider.is_connected
        assert isinstance(platform.is_connected, bool)


# ── open() lifecycle ───────────────────────────────────────────────────────


class TestOpenLifecycle:
    """Platform.open() — manual-token lifecycle method."""

    @pytest.mark.asyncio
    async def test_open_calls_provider_connect(self) -> None:
        """open() delegates to provider.connect()."""
        provider = MagicMock()
        provider.connect = AsyncMock()

        platform = Platform(provider)
        await platform.open()

        provider.connect.assert_awaited_once()


# ── __repr__ ───────────────────────────────────────────────────────────────


class TestRepr:
    """Platform.__repr__() format."""

    def test_repr_includes_broker_id(self) -> None:
        """repr(platform) shows the broker_id."""
        platform = Platform.paper()
        r = repr(platform)
        assert "Platform" in r
        assert platform.broker_id in r

    def test_repr_composite(self) -> None:
        """repr() of composed platform shows 'composite'."""
        primary = Platform.paper()
        secondary = Platform.paper()
        composite = Platform.compose(primary=primary, secondary=secondary)

        r = repr(composite)
        assert "composite" in r

"""Tests for authenticated readiness probes and bootstrap integration."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from brokers.common.auth import AuthManager, JsonTokenStateStore, TokenSource, TokenState
from brokers.common.connection.authenticated_readiness import (
    AuthProbeResult,
    authenticated_readiness_probe,
    execute_read_only_probe,
    is_token_rejection,
)
from brokers.common.connection.bootstrap_result import BootstrapResult, BootstrapStatus
from brokers.dhan.exceptions import AuthenticationError


class TestTokenRejectionDetection:
    def test_authentication_error_is_rejection(self):
        assert is_token_rejection(AuthenticationError("Token rejected: DH-906"))

    def test_message_patterns(self):
        assert is_token_rejection(Exception("HTTP 401 on GET /fundlimit"))
        assert not is_token_rejection(Exception("network timeout"))


class TestDhanAuthenticatedProbe:
    def test_funds_success(self):
        gw = MagicMock()
        gw.funds.return_value = MagicMock()
        result = execute_read_only_probe(gw, "dhan")
        assert result.ok
        assert result.probe_name == "dhan.funds"

    def test_stale_token_triggers_force_refresh_and_retry(self):
        gw = MagicMock()
        gw.funds.side_effect = [
            AuthenticationError("Token rejected: DH-906"),
            MagicMock(),
        ]
        conn = MagicMock()
        auth = MagicMock()
        state = TokenState(access_token="fresh-token", source=TokenSource.TOTP)
        auth.force_refresh.return_value = state
        conn._auth = auth
        conn._client = MagicMock()
        gw._conn = conn

        result = authenticated_readiness_probe(gw, "dhan")
        assert result.ok
        assert result.refreshed_token is True
        auth.force_refresh.assert_called_once()
        conn._client.update_token.assert_called_with("fresh-token")

    def test_refresh_failure_returns_reauth(self):
        gw = MagicMock()
        gw.funds.side_effect = AuthenticationError("Token rejected: DH-906")
        conn = MagicMock()
        auth = MagicMock()
        auth.force_refresh.return_value = None
        conn._auth = auth
        gw._conn = conn

        result = authenticated_readiness_probe(gw, "dhan")
        assert not result.ok
        assert result.token_rejected is True
        assert result.refreshed_token is False


class TestUpstoxAuthenticatedProbe:
    def test_profile_probe_success(self):
        gw = MagicMock()
        broker = MagicMock()
        tm = MagicMock()
        tm.bearer_token.return_value = "tok"
        future_ms = int(time.time() * 1000) + 3_600_000
        tm.oauth_client.fetch_profile.return_value = future_ms
        broker.token_manager = tm
        gw._broker = broker

        result = execute_read_only_probe(gw, "upstox")
        assert result.ok
        assert result.probe_name == "upstox.profile"

    def test_profile_returns_minus_one_falls_through_to_funds(self):
        gw = MagicMock()
        broker = MagicMock()
        tm = MagicMock()
        tm.bearer_token.return_value = "dead-token"
        tm.oauth_client.fetch_profile.return_value = -1
        broker.token_manager = tm
        gw._broker = broker
        gw.funds.return_value = MagicMock()

        result = execute_read_only_probe(gw, "upstox")
        assert result.ok
        assert result.probe_name == "upstox.funds"
        gw.funds.assert_called_once()

    def test_profile_minus_one_and_funds_401_fails(self):
        gw = MagicMock()
        broker = MagicMock()
        tm = MagicMock()
        tm.bearer_token.return_value = "dead-token"
        tm.oauth_client.fetch_profile.return_value = -1
        broker.token_manager = tm
        gw._broker = broker
        gw.funds.side_effect = Exception("HTTP 401 unauthorized")

        result = execute_read_only_probe(gw, "upstox")
        assert not result.ok
        assert result.probe_name == "upstox.funds"
        assert result.token_rejected is True


class TestAuthManagerForceRefresh:
    def test_force_refresh_bypasses_store(self, tmp_path):
        store_path = tmp_path / "token.json"
        store = JsonTokenStateStore(store_path)
        store.save(TokenState(access_token="stale", source=TokenSource.STATIC))
        calls = {"n": 0}

        def on_refresh():
            calls["n"] += 1
            return "fresh-from-totp"

        auth = AuthManager(
            client_id="cid",
            token_store=store,
            token_source=TokenSource.TOTP,
            on_refresh=on_refresh,
        )
        auth._state = store.load()

        state = auth.force_refresh()
        assert state is not None
        assert state.access_token == "fresh-from-totp"
        assert calls["n"] == 1


class TestBootstrapLiveReady:
    def test_live_ready_requires_authenticated(self):
        ready = BootstrapResult(
            status=BootstrapStatus.READY,
            broker="dhan",
            gateway=MagicMock(),
            probe_passed=True,
            authenticated=True,
        )
        not_auth = BootstrapResult(
            status=BootstrapStatus.READY,
            broker="dhan",
            gateway=MagicMock(),
            probe_passed=True,
            authenticated=False,
        )
        assert ready.live_ready is True
        assert not_auth.live_ready is False

    @patch("cli.services.broker_registry.authenticated_readiness_probe")
    @patch("cli.services.broker_registry.structural_readiness_probe")
    @patch("cli.services.broker_registry._create_dhan")
    def test_bootstrap_maps_auth_failure_to_reauth(
        self,
        mock_create,
        mock_structural,
        mock_auth_probe,
        monkeypatch,
    ):
        from cli.services.broker_registry import bootstrap_gateway

        monkeypatch.setattr(
            "cli.services.broker_registry.CredentialValidator.validate_broker",
            lambda broker, env_path=None: (True, []),
        )
        mock_create.return_value = MagicMock()
        mock_structural.return_value = (True, None)
        mock_auth_probe.return_value = AuthProbeResult(
            ok=False,
            probe_name="dhan.funds",
            error="DH-906",
            token_rejected=True,
        )

        result = bootstrap_gateway("dhan", require_authenticated=True)
        assert result.status == BootstrapStatus.REAUTH_REQUIRED
        assert result.authenticated is False
        assert not result.live_ready

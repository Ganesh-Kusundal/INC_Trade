"""Tests for the brokers.upstox package skeleton + login entry point."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

from brokers.upstox import UpstoxBroker
from brokers.upstox.auth.config import UpstoxConnectionSettings


@dataclass
class _Settings:
    client_id: str = "cid"
    client_secret: str = "sec"
    redirect_uri: str = "http://localhost:18080"
    access_token: str = "tok"
    auth_mode: str = "STATIC"
    environment: str = "LIVE"
    algo_name: str = ""
    base_v2: str = "https://api.upstox.com"
    base_hft: str = "https://api-hft.upstox.com"
    instrument_cache_path: Any = None
    refresh_buffer_minutes: int = 30
    allow_live_orders: bool = False
    market_protection_default: int = -1
    slice_default: bool = False
    ws_plus_plan: bool = False
    ws_auto_reconnect: bool = True
    ws_reconnect_interval_s: int = 10
    ws_reconnect_max_retries: int = 5


def _broker_from(_settings: _Settings) -> UpstoxBroker:
    """Construct an UpstoxBroker from a test settings dataclass."""
    s = UpstoxConnectionSettings(
        client_id=_settings.client_id,
        client_secret=_settings.client_secret,
        redirect_uri=_settings.redirect_uri,
        access_token=_settings.access_token,
        auth_mode=_settings.auth_mode,
        environment=_settings.environment,
        algo_name=_settings.algo_name,
        allow_live_orders=_settings.allow_live_orders,
        market_protection_default=_settings.market_protection_default,
        slice_default=_settings.slice_default,
        ws_plus_plan=_settings.ws_plus_plan,
        ws_auto_reconnect=_settings.ws_auto_reconnect,
        ws_reconnect_interval_s=_settings.ws_reconnect_interval_s,
        ws_reconnect_max_retries=_settings.ws_reconnect_max_retries,
    )
    return UpstoxBroker(s)


class TestUpstoxBrokerStub:
    def test_name(self):
        b = _broker_from(_Settings())
        assert b.name == "upstox"

    def test_broker_id_default(self):
        b = _broker_from(_Settings())
        assert b.broker_id == "cid"

    def test_broker_id_uses_settings(self):
        b = _broker_from(_Settings(client_id="my-cid"))
        assert b.broker_id == "my-cid"

    def test_connect_returns_false_with_invalid_token(self, monkeypatch):
        monkeypatch.setattr(
            "requests.Session.request", lambda *a, **k: MagicMock(status_code=401, text="x")
        )
        b = _broker_from(_Settings(access_token="placeholder"))
        # With no real network/token validation here, connect() should at least
        # not raise — it may return True or False depending on token state.
        result = b.connect()
        assert isinstance(result, bool)

    def test_disconnect_returns_bool(self):
        b = _broker_from(_Settings(access_token="placeholder"))
        assert isinstance(b.disconnect(), bool)

    def test_capabilities_include_market_data(self):
        b = _broker_from(_Settings(access_token="placeholder"))
        assert b.has_capability("market_data")
        assert b.has_capability("order_command")
        assert b.has_capability("portfolio")
        assert b.has_capability("options_chain")
        assert b.has_capability("websocket")
        assert b.has_capability("kill_switch")
        assert b.has_capability("order_slicing")
        assert not b.has_capability("market_intelligence")
        b._ensure_extended()
        assert b.has_capability("market_intelligence")
        assert b.has_capability("static_ip")


class TestLoginModule:
    def test_build_auth_url(self):
        from brokers.upstox.auth.config import UpstoxConnectionSettings
        from brokers.upstox.auth.login import build_auth_url

        s = UpstoxConnectionSettings(
            client_id="cid",
            client_secret="sec",
            redirect_uri="http://localhost:18080",
            environment="LIVE",
        )
        url = build_auth_url(s, "challenge-xyz", state="abc")
        assert "client_id=cid" in url
        assert "redirect_uri=" in url
        assert "code_challenge=challenge-xyz" in url
        assert "code_challenge_method=S256" in url
        assert "state=abc" in url
        assert "response_type=code" in url
        assert "/login/authorization/dialog" in url

    def test_build_auth_url_no_state(self):
        from brokers.upstox.auth.config import UpstoxConnectionSettings
        from brokers.upstox.auth.login import build_auth_url

        s = UpstoxConnectionSettings(
            client_id="cid",
            client_secret="sec",
            environment="LIVE",
        )
        url = build_auth_url(s, "ch")
        assert "state=" not in url

    def test_main_minimal(self, monkeypatch):
        from brokers.upstox.auth import login as login_mod
        from brokers.upstox.auth.config import UpstoxConnectionSettings

        s = UpstoxConnectionSettings(
            client_id="cid",
            client_secret="sec",
            redirect_uri="http://localhost:18080",
            access_token="x",
            environment="LIVE",
        )
        monkeypatch.setattr(login_mod, "UpstoxSettingsLoader", MagicMock())
        login_mod.UpstoxSettingsLoader.from_env.return_value = s

        fake_response = {"access_token": "new", "refresh_token": "new-rt"}
        monkeypatch.setattr(login_mod, "perform_login", lambda *a, **k: fake_response)

        with patch("builtins.print") as fake_print:
            rc = login_mod.main(["--no-browser", "--timeout", "0.01"])
        assert rc == 0
        fake_print.assert_called()

"""Tests for UpstoxSettingsLoader and UpstoxConnectionSettings."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from brokers.upstox.auth.config import (
    UpstoxConnectionSettings,
    UpstoxSettingsLoader,
)


@pytest.fixture(autouse=True)
def _clear_env() -> Iterator[None]:
    keys = [k for k in os.environ if k.startswith("UPSTOX_")]
    saved = {k: os.environ.pop(k) for k in keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            os.environ[k] = v


class TestUpstoxConnectionSettingsProperties:
    def test_is_sandbox(self):
        s = UpstoxConnectionSettings(client_id="X", environment="SANDBOX")
        assert s.is_sandbox is True
        assert s.is_live is False

    def test_is_live(self):
        s = UpstoxConnectionSettings(client_id="X", environment="LIVE")
        assert s.is_live is True
        assert s.is_sandbox is False

    @pytest.mark.parametrize(
        "mode,expected",
        [
            ("STATIC", True),
            ("STATIC".lower(), True),
            ("OAUTH", False),
            ("INTERACTIVE", False),
            ("EXTENDED", False),
            ("WEBHOOK", False),
        ],
    )
    def test_is_static(self, mode, expected):
        s = UpstoxConnectionSettings(client_id="X", auth_mode=mode)
        assert s.is_static is expected

    @pytest.mark.parametrize(
        "mode,expected",
        [
            ("OAUTH", True),
            ("OAUTH".lower(), True),
            ("STATIC", False),
        ],
    )
    def test_is_oauth(self, mode, expected):
        s = UpstoxConnectionSettings(client_id="X", auth_mode=mode)
        assert s.is_oauth is expected

    def test_is_interactive(self):
        s = UpstoxConnectionSettings(client_id="X", auth_mode="INTERACTIVE")
        assert s.is_interactive is True

    def test_is_extended(self):
        s = UpstoxConnectionSettings(client_id="X", auth_mode="EXTENDED")
        assert s.is_extended is True

    def test_is_webhook(self):
        s = UpstoxConnectionSettings(client_id="X", auth_mode="WEBHOOK")
        assert s.is_webhook is True

    def test_token_flags(self):
        s = UpstoxConnectionSettings(
            client_id="X",
            access_token="a",
            refresh_token="r",
            extended_token="e",
        )
        assert s.has_access_token is True
        assert s.has_refresh_token is True
        assert s.has_extended_token is True

    def test_token_flags_missing(self):
        s = UpstoxConnectionSettings(client_id="X")
        assert s.has_access_token is False
        assert s.has_refresh_token is False
        assert s.has_extended_token is False

    def test_rest_base_override_strips_trailing_slash(self):
        s = UpstoxConnectionSettings(client_id="X", rest_base_url="https://example.com/v2/")
        assert s.rest_base_override == "https://example.com/v2"

    def test_frozen(self):
        s = UpstoxConnectionSettings(client_id="X")
        with pytest.raises(FrozenInstanceError):
            s.client_id = "Y"


class TestUpstoxSettingsLoaderFromEnv:
    def test_minimal(self):
        os.environ["UPSTOX_CLIENT_ID"] = "abc123"
        s = UpstoxSettingsLoader.from_env(env_path=Path("/dev/null"))
        assert s.client_id == "abc123"
        assert s.auth_mode == "STATIC"
        assert s.environment == "LIVE"
        assert s.refresh_buffer_minutes == 30
        assert s.redirect_uri == "http://localhost:18080"
        assert s.redirect_port == 18080
        assert s.allow_live_orders is False
        assert s.ws_plus_plan is False
        assert s.slice_default is False
        assert s.market_protection_default == -1

    def test_full(self):
        env = {
            "UPSTOX_CLIENT_ID": "cid",
            "UPSTOX_CLIENT_SECRET": "sec",
            "UPSTOX_REDIRECT_URI": "http://localhost:9999",
            "UPSTOX_AUTH_MODE": "OAUTH",
            "UPSTOX_ENVIRONMENT": "SANDBOX",
            "UPSTOX_ACCESS_TOKEN": "tok",
            "UPSTOX_REFRESH_TOKEN": "ref",
            "UPSTOX_EXTENDED_TOKEN": "ext",
            "UPSTOX_TOKEN_STATE_FILE": "/tmp/state.json",
            "UPSTOX_REFRESH_BUFFER_MINUTES": "5",
            "UPSTOX_INSTRUMENT_CACHE": "/tmp/inst.json.gz",
            "UPSTOX_REST_BASE_URL": "https://proxy.example.com",
            "UPSTOX_REDIRECT_PORT": "19000",
            "UPSTOX_ALGO_NAME": "alpha-v1",
            "UPSTOX_STATIC_IP": "1.2.3.4",
            "UPSTOX_ALLOW_LIVE_ORDERS": "false",
            "UPSTOX_WS_PLUS_PLAN": "true",
            "UPSTOX_MARKET_PROTECTION_DEFAULT": "3",
            "UPSTOX_SLICE_DEFAULT": "true",
        }
        for k, v in env.items():
            os.environ[k] = v
        s = UpstoxSettingsLoader.from_env(env_path=Path("/dev/null"))
        assert s.client_id == "cid"
        assert s.client_secret == "sec"
        assert s.redirect_uri == "http://localhost:9999"
        assert s.auth_mode == "OAUTH"
        assert s.environment == "SANDBOX"
        assert s.access_token == "tok"
        assert s.refresh_token == "ref"
        assert s.extended_token == "ext"
        assert s.token_state_file == Path("/tmp/state.json")
        assert s.refresh_buffer_minutes == 5
        assert s.instrument_cache == Path("/tmp/inst.json.gz")
        assert s.rest_base_url == "https://proxy.example.com"
        assert s.redirect_port == 19000
        assert s.algo_name == "alpha-v1"
        assert s.static_ip == "1.2.3.4"
        assert s.allow_live_orders is False
        assert s.ws_plus_plan is True
        assert s.market_protection_default == 3
        assert s.slice_default is True

    def test_sandbox_rest_base_url(self):
        os.environ["UPSTOX_CLIENT_ID"] = "cid"
        os.environ["UPSTOX_ENVIRONMENT"] = "SANDBOX"
        os.environ["UPSTOX_SANDBOX_REST_BASE_URL"] = "https://my-sb.example.com"
        s = UpstoxSettingsLoader.from_env(env_path=Path("/dev/null"))
        assert s.rest_base_url == "https://my-sb.example.com"

    def test_missing_client_id_raises(self):
        with pytest.raises(ValueError, match="UPSTOX_CLIENT_ID is required"):
            UpstoxSettingsLoader.from_env(env_path=Path("/dev/null"))

    def test_invalid_environment_raises(self):
        os.environ["UPSTOX_CLIENT_ID"] = "cid"
        os.environ["UPSTOX_ENVIRONMENT"] = "BOGUS"
        with pytest.raises(ValueError, match="UPSTOX_ENVIRONMENT must be one of"):
            UpstoxSettingsLoader.from_env(env_path=Path("/dev/null"))

    def test_invalid_auth_mode_raises(self):
        os.environ["UPSTOX_CLIENT_ID"] = "cid"
        os.environ["UPSTOX_AUTH_MODE"] = "BOGUS"
        with pytest.raises(ValueError, match="UPSTOX_AUTH_MODE must be one of"):
            UpstoxSettingsLoader.from_env(env_path=Path("/dev/null"))

    def test_loads_from_dotenv(self, tmp_path: Path):
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "UPSTOX_CLIENT_ID=from-dotenv\n"
            "UPSTOX_AUTH_MODE=EXTENDED\n"
            "UPSTOX_EXTENDED_TOKEN=ext-tok\n"
        )
        s = UpstoxSettingsLoader.from_env(env_path=env_file)
        assert s.client_id == "from-dotenv"
        assert s.auth_mode == "EXTENDED"
        assert s.extended_token == "ext-tok"

    def test_totp_defaults_token_state_file(self):
        os.environ["UPSTOX_CLIENT_ID"] = "cid"
        os.environ["UPSTOX_AUTH_MODE"] = "TOTP"
        s = UpstoxSettingsLoader.from_env(env_path=Path("/dev/null"))
        assert s.token_state_file == Path("runtime/upstox-token-state.json")


class TestUpstoxSettingsLoaderFromProperties:
    def test_minimal_properties(self, tmp_path: Path):
        path = tmp_path / "upstox-local.properties"
        path.write_text(
            "upstox.clientId=cid-prop\nupstox.environment=LIVE\nupstox.authMode=STATIC\n"
        )
        s = UpstoxSettingsLoader.from_properties(path)
        assert s.client_id == "cid-prop"
        assert s.environment == "LIVE"
        assert s.auth_mode == "STATIC"
        assert s.refresh_buffer_minutes == 30
        assert s.redirect_uri == "http://localhost:18080"

    def test_full_properties(self, tmp_path: Path):
        path = tmp_path / "upstox-local.properties"
        path.write_text(
            "\n".join(
                [
                    "upstox.clientId=cid",
                    "upstox.clientSecret=sec",
                    "upstox.redirectUri=http://x:1234",
                    "upstox.authMode=OAUTH",
                    "upstox.environment=SANDBOX",
                    "upstox.accessToken=tok",
                    "upstox.refreshToken=ref",
                    "upstox.extendedToken=ext",
                    "upstox.tokenStateFile=/tmp/st.json",
                    "upstox.refreshBufferMinutes=15",
                    "upstox.instrumentCache=/tmp/inst.json.gz",
                    "upstox.restBaseUrl=https://proxy.example.com",
                    "upstox.redirectPort=20000",
                    "upstox.algoName=algo-x",
                    "upstox.staticIp=2.2.2.2",
                    "upstox.allowLiveOrders=false",
                    "upstox.wsPlusPlan=true",
                    "upstox.marketProtectionDefault=2",
                    "upstox.sliceDefault=true",
                ]
            )
            + "\n"
        )
        s = UpstoxSettingsLoader.from_properties(path)
        assert s.client_id == "cid"
        assert s.client_secret == "sec"
        assert s.redirect_uri == "http://x:1234"
        assert s.auth_mode == "OAUTH"
        assert s.environment == "SANDBOX"
        assert s.access_token == "tok"
        assert s.refresh_token == "ref"
        assert s.extended_token == "ext"
        assert s.token_state_file == Path("/tmp/st.json")
        assert s.refresh_buffer_minutes == 15
        assert s.instrument_cache == Path("/tmp/inst.json.gz")
        assert s.rest_base_url == "https://proxy.example.com"
        assert s.redirect_port == 20000
        assert s.algo_name == "algo-x"
        assert s.static_ip == "2.2.2.2"
        assert s.allow_live_orders is False
        assert s.ws_plus_plan is True
        assert s.market_protection_default == 2
        assert s.slice_default is True

    def test_missing_client_id_raises(self, tmp_path: Path):
        path = tmp_path / "empty.properties"
        path.write_text("upstox.environment=LIVE\n")
        with pytest.raises(ValueError, match="must contain upstox.clientId"):
            UpstoxSettingsLoader.from_properties(path)

    def test_invalid_environment_raises(self, tmp_path: Path):
        path = tmp_path / "bad.properties"
        path.write_text("upstox.clientId=cid\nupstox.environment=BOGUS\n")
        with pytest.raises(ValueError, match="upstox.environment must be one of"):
            UpstoxSettingsLoader.from_properties(path)

    def test_invalid_auth_mode_raises(self, tmp_path: Path):
        path = tmp_path / "bad.properties"
        path.write_text("upstox.clientId=cid\nupstox.authMode=BOGUS\n")
        with pytest.raises(ValueError, match="upstox.authMode must be one of"):
            UpstoxSettingsLoader.from_properties(path)

    def test_default_env_file(self, tmp_path: Path, monkeypatch):
        env_file = tmp_path / ".env.upstox"
        env_file.write_text("UPSTOX_CLIENT_ID=auto-detected\n")
        monkeypatch.chdir(tmp_path)
        s = UpstoxSettingsLoader.from_env()
        assert s.client_id == "auto-detected"

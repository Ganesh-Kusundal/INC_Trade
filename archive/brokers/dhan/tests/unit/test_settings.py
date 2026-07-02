"""Unit tests for DhanConnectionSettings and DhanSettingsLoader."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from brokers.dhan.settings import (
    _BASE_URL,
    _GENERATE_TOKEN_URL,
    DhanConnectionSettings,
    DhanSettingsLoader,
)
from domain.constants.auth import (
    DHAN_TOKEN_LIFETIME_SECONDS,
    DHAN_TOKEN_REFRESH_BUFFER_SECONDS,
    DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS,
)


@pytest.fixture(autouse=True)
def _clear_env() -> Iterator[None]:
    """Remove DHAN_* env vars before each test, restoring them after."""
    keys = [k for k in os.environ if k.startswith("DHAN_")]
    saved = {k: os.environ.pop(k) for k in keys}
    try:
        yield
    finally:
        for k, v in saved.items():
            os.environ[k] = v


class TestDhanConnectionSettingsProperties:
    """Test derived properties and frozen-ness of DhanConnectionSettings."""

    def test_has_access_token_true(self):
        s = DhanConnectionSettings(client_id="X", access_token="tok")
        assert s.has_access_token is True

    def test_has_access_token_false(self):
        s = DhanConnectionSettings(client_id="X")
        assert s.has_access_token is False

    def test_has_totp_true(self):
        s = DhanConnectionSettings(client_id="X", pin="1234", totp_secret="SECRET")
        assert s.has_totp is True

    def test_has_totp_false_no_pin(self):
        s = DhanConnectionSettings(client_id="X", totp_secret="SECRET")
        assert s.has_totp is False

    def test_has_totp_false_no_secret(self):
        s = DhanConnectionSettings(client_id="X", pin="1234")
        assert s.has_totp is False

    def test_has_totp_false_both_missing(self):
        s = DhanConnectionSettings(client_id="X")
        assert s.has_totp is False

    def test_generate_token_url_constant(self):
        s = DhanConnectionSettings(client_id="X")
        assert s.generate_token_url == _GENERATE_TOKEN_URL

    def test_default_base_url(self):
        s = DhanConnectionSettings(client_id="X")
        assert s.base_url == _BASE_URL

    def test_custom_base_url(self):
        s = DhanConnectionSettings(client_id="X", base_url="https://custom.example.com")
        assert s.base_url == "https://custom.example.com"

    def test_default_timeout(self):
        s = DhanConnectionSettings(client_id="X")
        assert s.http_timeout == 15.0

    def test_default_lifetimes(self):
        s = DhanConnectionSettings(client_id="X")
        assert s.token_lifetime_seconds == DHAN_TOKEN_LIFETIME_SECONDS
        assert s.scheduler_interval_seconds == DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS
        assert s.refresh_buffer_seconds == DHAN_TOKEN_REFRESH_BUFFER_SECONDS

    def test_frozen(self):
        s = DhanConnectionSettings(client_id="X")
        with pytest.raises(FrozenInstanceError):
            s.client_id = "Y"


class TestDhanSettingsLoaderFromEnv:
    """Test DhanSettingsLoader.from_env() with various env var configurations."""

    def test_minimal(self):
        """Only client_id set — all other fields use defaults."""
        os.environ["DHAN_CLIENT_ID"] = "dhan123"
        s = DhanSettingsLoader.from_env(env_path=Path("/dev/null"))
        assert s.client_id == "dhan123"
        assert s.access_token == ""
        assert s.base_url == _BASE_URL
        assert s.http_timeout == 15.0
        assert s.enable_retry is True
        assert s.pin == ""
        assert s.totp_secret == ""
        assert s.token_lifetime_seconds == DHAN_TOKEN_LIFETIME_SECONDS
        assert s.scheduler_interval_seconds == DHAN_TOKEN_SCHEDULER_INTERVAL_SECONDS
        assert s.refresh_buffer_seconds == DHAN_TOKEN_REFRESH_BUFFER_SECONDS

    def test_full(self):
        """All env vars set — every field populated."""
        env = {
            "DHAN_CLIENT_ID": "cid",
            "DHAN_ACCESS_TOKEN": "tok123",
            "DHAN_BASE_URL": "https://custom.dhan.co/api",
            "DHAN_HTTP_TIMEOUT": "30.0",
            "DHAN_ENABLE_RETRY": "false",
            "DHAN_PIN": "4321",
            "DHAN_TOTP_SECRET": "TOTPSEC",
            "DHAN_TOKEN_LIFETIME_SECONDS": "43200",
            "DHAN_SCHEDULER_INTERVAL_SECONDS": "600",
            "DHAN_REFRESH_BUFFER_SECONDS": "120",
        }
        for k, v in env.items():
            os.environ[k] = v
        s = DhanSettingsLoader.from_env(env_path=Path("/dev/null"))
        assert s.client_id == "cid"
        assert s.access_token == "tok123"
        assert s.base_url == "https://custom.dhan.co/api"
        assert s.http_timeout == 30.0
        assert s.enable_retry is False
        assert s.pin == "4321"
        assert s.totp_secret == "TOTPSEC"
        assert s.token_lifetime_seconds == 43200
        assert s.scheduler_interval_seconds == 600
        assert s.refresh_buffer_seconds == 120

    def test_custom_prefix(self):
        """Custom prefix instead of default DHAN."""
        os.environ["MYBROKER_CLIENT_ID"] = "my-cid"
        s = DhanSettingsLoader.from_env(env_path=Path("/dev/null"), prefix="MYBROKER")
        assert s.client_id == "my-cid"

    def test_missing_client_id_raises(self):
        """No client_id set — ValueError raised."""
        with pytest.raises(ValueError, match="DHAN_CLIENT_ID is required"):
            DhanSettingsLoader.from_env(env_path=Path("/dev/null"))

    def test_loads_from_dotenv(self, tmp_path: Path):
        """Env file is loaded and values become available."""
        env_file = tmp_path / ".env.local"
        env_file.write_text(
            "DHAN_CLIENT_ID=from-dotenv\nDHAN_ACCESS_TOKEN=dotenv-tok\nDHAN_PIN=9999\n"
        )
        s = DhanSettingsLoader.from_env(env_path=env_file)
        assert s.client_id == "from-dotenv"
        assert s.access_token == "dotenv-tok"
        assert s.pin == "9999"

    def test_env_file_overrides_env(self, tmp_path: Path):
        """Env file values take precedence over pre-existing env vars."""
        os.environ["DHAN_CLIENT_ID"] = "pre-existing"
        env_file = tmp_path / ".env"
        env_file.write_text("DHAN_CLIENT_ID=from-file\n")
        s = DhanSettingsLoader.from_env(env_path=env_file)
        # load_env_file sets os.environ, which overwrites the pre-existing value
        assert s.client_id == "from-file"

    def test_bool_parsing_true_variants(self):
        """Various truthy values for enable_retry."""
        os.environ["DHAN_CLIENT_ID"] = "cid"
        # Start from known-false to confirm parsing actually flips the value
        os.environ["DHAN_ENABLE_RETRY"] = "0"
        s = DhanSettingsLoader.from_env(env_path=Path("/dev/null"))
        assert s.enable_retry is False
        for val in ("1", "true", "yes", "y", "on"):
            os.environ["DHAN_ENABLE_RETRY"] = val
            s = DhanSettingsLoader.from_env(env_path=Path("/dev/null"))
            assert s.enable_retry is True, f"expected True for {val!r}"

    def test_bool_parsing_false_variants(self):
        """Various falsy values for enable_retry."""
        os.environ["DHAN_CLIENT_ID"] = "cid"
        for val in ("0", "false", "no", "n", "off"):
            os.environ["DHAN_ENABLE_RETRY"] = val
            s = DhanSettingsLoader.from_env(env_path=Path("/dev/null"))
            assert s.enable_retry is False, f"expected False for {val!r}"

    def test_invalid_int_falls_back(self):
        """Non-numeric int env var uses default."""
        os.environ["DHAN_CLIENT_ID"] = "cid"
        os.environ["DHAN_HTTP_TIMEOUT"] = "not-a-number"
        s = DhanSettingsLoader.from_env(env_path=Path("/dev/null"))
        assert s.http_timeout == 15.0  # default

    def test_invalid_float_falls_back(self):
        """Non-parseable float uses default."""
        os.environ["DHAN_CLIENT_ID"] = "cid"
        os.environ["DHAN_TOKEN_LIFETIME_SECONDS"] = "nan"
        s = DhanSettingsLoader.from_env(env_path=Path("/dev/null"))
        assert s.token_lifetime_seconds == DHAN_TOKEN_LIFETIME_SECONDS  # default

    def test_empty_env_var_uses_default(self):
        """Empty string env var uses default."""
        os.environ["DHAN_CLIENT_ID"] = "cid"
        os.environ["DHAN_BASE_URL"] = ""
        s = DhanSettingsLoader.from_env(env_path=Path("/dev/null"))
        assert s.base_url == _BASE_URL  # default, not empty string


class TestDhanSettingsLoaderFromDict:
    """Test DhanSettingsLoader.from_dict() for .properties-style loading."""

    def test_minimal(self):
        """Only clientId set."""
        s = DhanSettingsLoader.from_dict({"DHAN.clientId": "dict-cid"}, prefix="DHAN")
        assert s.client_id == "dict-cid"
        assert s.access_token == ""
        assert s.base_url == _BASE_URL

    def test_full(self):
        """All fields populated."""
        d = {
            "DHAN.clientId": "cid",
            "DHAN.accessToken": "tok",
            "DHAN.baseUrl": "https://custom.api",
            "DHAN.httpTimeout": "20.0",
            "DHAN.enableRetry": "false",
            "DHAN.pin": "1234",
            "DHAN.totpSecret": "TOTP",
            "DHAN.tokenLifetimeSeconds": "10000",
            "DHAN.schedulerIntervalSeconds": "300",
            "DHAN.refreshBufferSeconds": "60",
        }
        s = DhanSettingsLoader.from_dict(d, prefix="DHAN")
        assert s.client_id == "cid"
        assert s.access_token == "tok"
        assert s.base_url == "https://custom.api"
        assert s.http_timeout == 20.0
        assert s.enable_retry is False
        assert s.pin == "1234"
        assert s.totp_secret == "TOTP"
        assert s.token_lifetime_seconds == 10000
        assert s.scheduler_interval_seconds == 300
        assert s.refresh_buffer_seconds == 60

    def test_underscore_keys(self):
        """Underscore-separated keys (e.g. access_token) also work."""
        d = {"DHAN.client_id": "cid", "DHAN.access_token": "tok"}
        s = DhanSettingsLoader.from_dict(d, prefix="DHAN")
        assert s.client_id == "cid"
        assert s.access_token == "tok"

    def test_missing_client_id_raises(self):
        """No clientId in dict — ValueError raised."""
        with pytest.raises(ValueError, match="clientId is required"):
            DhanSettingsLoader.from_dict({}, prefix="DHAN")

    def test_invalid_int_falls_back(self):
        """Non-numeric int field uses default."""
        d = {"DHAN.clientId": "cid", "DHAN.tokenLifetimeSeconds": "bad"}
        s = DhanSettingsLoader.from_dict(d, prefix="DHAN")
        assert s.token_lifetime_seconds == DHAN_TOKEN_LIFETIME_SECONDS  # default

    def test_invalid_float_falls_back(self):
        """Non-numeric float field uses default."""
        d = {"DHAN.clientId": "cid", "DHAN.httpTimeout": "bad"}
        s = DhanSettingsLoader.from_dict(d, prefix="DHAN")
        assert s.http_timeout == 15.0  # default

    def test_bool_false(self):
        """Boolean false parsed correctly."""
        d = {"DHAN.clientId": "cid", "DHAN.enableRetry": "false"}
        s = DhanSettingsLoader.from_dict(d, prefix="DHAN")
        assert s.enable_retry is False

    def test_bool_true(self):
        """Boolean true parsed correctly."""
        d = {"DHAN.clientId": "cid", "DHAN.enableRetry": "true"}
        s = DhanSettingsLoader.from_dict(d, prefix="DHAN")
        assert s.enable_retry is True


class TestDhanSettingsLoaderDefaultEnvFile:
    """Test that from_env() auto-detects .env.local / .env files."""

    def test_dotenv_local_auto_detect(self, tmp_path: Path, monkeypatch):
        """from_env() without env_path picks up .env.local in cwd."""
        env_file = tmp_path / ".env.local"
        env_file.write_text("DHAN_CLIENT_ID=auto-cid\n")
        monkeypatch.chdir(tmp_path)
        s = DhanSettingsLoader.from_env()
        assert s.client_id == "auto-cid"

    def test_dotenv_fallback(self, tmp_path: Path, monkeypatch):
        """from_env() falls back to .env if .env.local is absent."""
        env_file = tmp_path / ".env"
        env_file.write_text("DHAN_CLIENT_ID=fallback-cid\n")
        monkeypatch.chdir(tmp_path)
        s = DhanSettingsLoader.from_env()
        assert s.client_id == "fallback-cid"

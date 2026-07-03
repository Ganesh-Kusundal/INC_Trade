"""Tests for config schema, defaults, and environment profiles."""

import os

import pytest

from brokers.config.schema import (
    ApiConfig,
    AppConfig,
    DhanConfig,
    TradingConfig,
    UpstoxConfig,
    load_api_config,
    load_dhan_config,
    load_trading_config,
    load_upstox_config,
)
from brokers.config.defaults import DEFAULT_CONFIG, get_config, reset_config
from brokers.config.profiles import load_profile
from brokers.config.profiles.dev import DevProfile
from brokers.config.profiles.staging import StagingProfile
from brokers.config.profiles.prod import ProdProfile


class TestAppConfig:
    def test_from_env_defaults(self, monkeypatch):
        for key in list(os.environ):
            if key.startswith("TRADEX_") or key.startswith("XV2_"):
                monkeypatch.delenv(key, raising=False)
        cfg = AppConfig.from_env()
        assert hasattr(cfg, "api_port")
        assert hasattr(cfg, "api_host")
        assert hasattr(cfg, "app_env")

    def test_traDEX_prefix_precedence(self, monkeypatch):
        monkeypatch.setenv("TRADEX_API_PORT", "9999")
        monkeypatch.setenv("XV2_API_PORT", "1111")
        cfg = AppConfig.from_env()
        assert cfg.api_port == 9999

    def test_legacy_alias_fallback(self, monkeypatch):
        monkeypatch.delenv("TRADEX_API_PORT", raising=False)
        monkeypatch.setenv("API_PORT", "7777")
        cfg = AppConfig.from_env()
        assert cfg.api_port == 7777


class TestDhanConfig:
    def test_load_from_env(self, monkeypatch):
        monkeypatch.setenv("DHAN_CLIENT_ID", "my_client")
        monkeypatch.setenv("DHAN_ACCESS_TOKEN", "my_token")
        cfg = load_dhan_config()
        assert cfg.client_id == "my_client"
        assert cfg.access_token == "my_token"

    def test_defaults(self, monkeypatch):
        for key in list(os.environ):
            if "DHAN" in key:
                monkeypatch.delenv(key, raising=False)
        cfg = load_dhan_config()
        assert cfg.allow_live_orders is False


class TestUpstoxConfig:
    def test_load_from_env(self, monkeypatch):
        monkeypatch.setenv("UPSTOX_CLIENT_ID", "upstox_client")
        cfg = load_upstox_config()
        assert cfg.client_id == "upstox_client"


class TestApiConfig:
    def test_load_api_config(self):
        cfg = load_api_config()
        assert cfg is not None
        assert hasattr(cfg, "api_key")


class TestTradingConfig:
    def test_load_trading_config(self):
        cfg = load_trading_config()
        assert cfg is not None


class TestDefaults:
    def test_get_config_returns_app_config(self):
        reset_config()
        cfg = get_config()
        assert isinstance(cfg, AppConfig)

    def test_get_config_cached(self):
        reset_config()
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

    def test_reset_drops_cache(self):
        reset_config()
        cfg1 = get_config()
        reset_config()
        cfg2 = get_config()
        assert cfg1 is not cfg2

    def test_default_config_dict(self):
        assert "api_port" in DEFAULT_CONFIG
        assert "api_host" in DEFAULT_CONFIG


class TestProfiles:
    def test_load_dev_profile(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "dev")
        profile = load_profile()
        assert isinstance(profile, DevProfile)
        assert profile.name == "dev"
        assert profile.debug_enabled is True
        assert profile.mock_brokers_allowed is True

    def test_load_staging_profile(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "staging")
        profile = load_profile()
        assert isinstance(profile, StagingProfile)
        assert profile.name == "staging"
        assert profile.strict_validation is True
        assert profile.encryption_required is True

    def test_load_prod_profile(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "prod")
        profile = load_profile()
        assert isinstance(profile, ProdProfile)
        assert profile.name == "prod"
        assert profile.debug_enabled is False
        assert profile.allow_live_orders_by_default is False

    def test_unknown_env_raises(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "unknown")
        with pytest.raises(ValueError, match="Unknown profile"):
            load_profile()

    def test_profile_to_dict(self):
        profile = DevProfile()
        d = profile.to_dict()
        assert "name" in d
        assert "log_level" in d
        assert d["name"] == "dev"

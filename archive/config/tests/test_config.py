"""Tests for central AppConfig and defaults module."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from config.defaults import DEFAULT_CONFIG, get_config, reset_config
from config.schema import AppConfig


class TestAppConfigDefaults:
    """Verify default values match the spec."""

    def test_default_app_env(self) -> None:
        cfg = AppConfig()
        assert cfg.app_env == "dev"

    def test_default_log_level(self) -> None:
        cfg = AppConfig()
        assert cfg.log_level == "INFO"

    def test_default_debug(self) -> None:
        cfg = AppConfig()
        assert cfg.debug is False

    def test_default_redis_url(self) -> None:
        cfg = AppConfig()
        assert cfg.redis_url is None

    def test_default_api_host(self) -> None:
        cfg = AppConfig()
        assert cfg.api_host == "127.0.0.1"

    def test_default_api_port(self) -> None:
        cfg = AppConfig()
        assert cfg.api_port == 8000

    def test_default_observability_port(self) -> None:
        cfg = AppConfig()
        assert cfg.observability_port == 8765

    def test_default_cors_origins(self) -> None:
        cfg = AppConfig()
        assert cfg.cors_origins == ["http://localhost:5173"]

    def test_default_rate_limit_max_requests(self) -> None:
        cfg = AppConfig()
        assert cfg.rate_limit_max_requests == 0

    def test_default_rate_limit_window_seconds(self) -> None:
        cfg = AppConfig()
        assert cfg.rate_limit_window_seconds == 60.0


class TestEnvVarLoading:
    """Verify from_env reads environment variables correctly."""

    def test_from_env_with_traex_prefix(self) -> None:
        env = {
            "TRADEX_APP_ENV": "staging",
            "TRADEX_LOG_LEVEL": "DEBUG",
            "TRADEX_DEBUG": "1",
            "TRADEX_REDIS_URL": "redis://localhost:6379",
            "TRADEX_API_HOST": "0.0.0.0",
            "TRADEX_API_PORT": "9000",
            "TRADEX_OBSERVABILITY_PORT": "9999",
            "TRADEX_CORS_ORIGINS": "http://a.com,http://b.com",
            "TRADEX_RATE_LIMIT_MAX_REQUESTS": "50",
            "TRADEX_RATE_LIMIT_WINDOW_SECONDS": "30.0",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = AppConfig.from_env()

        assert cfg.app_env == "staging"
        assert cfg.log_level == "DEBUG"
        assert cfg.debug is True
        assert cfg.redis_url == "redis://localhost:6379"
        assert cfg.api_host == "0.0.0.0"
        assert cfg.api_port == 9000
        assert cfg.observability_port == 9999
        assert cfg.cors_origins == ["http://a.com", "http://b.com"]
        assert cfg.rate_limit_max_requests == 50
        assert cfg.rate_limit_window_seconds == 30.0

    def test_from_env_legacy_vars(self) -> None:
        env = {
            "APP_ENV": "prod",
            "XV2_LOG_LEVEL": "WARNING",
            "TRADEXV2_DEBUG": "true",
            "REDIS_URL": "redis://prod:6379",
            "API_HOST": "10.0.0.1",
            "API_PORT": "3000",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = AppConfig.from_env()

        assert cfg.app_env == "prod"
        assert cfg.log_level == "WARNING"
        assert cfg.debug is True
        assert cfg.redis_url == "redis://prod:6379"
        assert cfg.api_host == "10.0.0.1"
        assert cfg.api_port == 3000

    def test_from_env_prefers_traex_over_legacy(self) -> None:
        env = {
            "TRADEX_APP_ENV": "staging",
            "APP_ENV": "prod",
            "TRADEX_LOG_LEVEL": "ERROR",
            "XV2_LOG_LEVEL": "DEBUG",
        }
        with patch.dict(os.environ, env, clear=False):
            cfg = AppConfig.from_env()

        assert cfg.app_env == "staging"
        assert cfg.log_level == "ERROR"

    def test_from_env_empty_uses_defaults(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cfg = AppConfig.from_env()

        assert cfg.app_env == "dev"
        assert cfg.log_level == "INFO"
        assert cfg.debug is False
        assert cfg.redis_url is None
        assert cfg.api_port == 8000


class TestValidation:
    """Verify field validators reject invalid values."""

    def test_invalid_log_level_raises(self) -> None:
        with pytest.raises(ValidationError, match="Invalid log level"):
            AppConfig(log_level="BANANAS")

    def test_log_level_case_insensitive(self) -> None:
        cfg = AppConfig(log_level="debug")
        assert cfg.log_level == "DEBUG"

    def test_port_zero_raises(self) -> None:
        with pytest.raises(ValidationError, match="Port must be > 0"):
            AppConfig(api_port=0)

    def test_negative_port_raises(self) -> None:
        with pytest.raises(ValidationError, match="Port must be > 0"):
            AppConfig(observability_port=-1)

    def test_valid_log_levels_accepted(self) -> None:
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            cfg = AppConfig(log_level=level)
            assert cfg.log_level == level

    def test_valid_app_env_accepted(self) -> None:
        for env in ("dev", "staging", "prod"):
            cfg = AppConfig(app_env=env)
            assert cfg.app_env == env


class TestFromEnvFactory:
    """Test the from_env classmethod edge cases."""

    def test_from_env_with_none_redis(self) -> None:
        env = {"TRADEX_REDIS_URL": ""}
        with patch.dict(os.environ, env, clear=False):
            cfg = AppConfig.from_env()
        assert cfg.redis_url is None

    def test_from_env_cors_empty_string(self) -> None:
        env = {"TRADEX_CORS_ORIGINS": ""}
        with patch.dict(os.environ, env, clear=False):
            cfg = AppConfig.from_env()
        assert cfg.cors_origins == ["http://localhost:5173"]


class TestDefaultsModule:
    """Test the cached get_config / reset_config helpers."""

    def setup_method(self) -> None:
        reset_config()

    def teardown_method(self) -> None:
        reset_config()

    def test_get_config_returns_app_config(self) -> None:
        cfg = get_config()
        assert isinstance(cfg, AppConfig)

    def test_get_config_caches(self) -> None:
        cfg1 = get_config()
        cfg2 = get_config()
        assert cfg1 is cfg2

    def test_reset_config_clears_cache(self) -> None:
        cfg1 = get_config()
        reset_config()
        cfg2 = get_config()
        assert cfg1 is not cfg2

    def test_default_config_dict_keys(self) -> None:
        expected_keys = {
            "app_env",
            "log_level",
            "debug",
            "redis_url",
            "api_host",
            "api_port",
            "observability_port",
            "cors_origins",
            "rate_limit_max_requests",
            "rate_limit_window_seconds",
        }
        assert set(DEFAULT_CONFIG.keys()) == expected_keys


class TestNestedConfig:
    """Test nested/complex field handling."""

    def test_cors_origins_as_list(self) -> None:
        origins = ["http://a.com", "http://b.com", "http://c.com"]
        cfg = AppConfig(cors_origins=origins)
        assert cfg.cors_origins == origins
        assert len(cfg.cors_origins) == 3

    def test_cors_origins_from_env_comma_separated(self) -> None:
        env = {"TRADEX_CORS_ORIGINS": "http://x.com, http://y.com ,http://z.com"}
        with patch.dict(os.environ, env, clear=False):
            cfg = AppConfig.from_env()
        assert cfg.cors_origins == ["http://x.com", "http://y.com", "http://z.com"]

    def test_model_dump_roundtrip(self) -> None:
        cfg = AppConfig(app_env="staging", debug=True, cors_origins=["http://test.com"])
        data = cfg.model_dump()
        restored = AppConfig(**data)
        assert restored == cfg

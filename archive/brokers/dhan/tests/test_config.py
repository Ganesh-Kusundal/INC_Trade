"""Tests for Dhan broker configuration system.

Tests cover:
  - Configuration dataclasses (DhanResilienceConfig, DhanRateLimitConfig, etc.)
  - Configuration loading from environment variables
  - Configuration loading from files
  - Backwards compatibility with hardcoded defaults
  - Configuration integration with DhanHttpClient
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from brokers.dhan.config import (
    DhanCircuitBreakerConfig,
    DhanRateLimitConfig,
    DhanResilienceConfig,
    DhanRetryConfig,
    DhanTokenConfig,
    DEFAULT_CONFIG,
    DEFAULT_BASE_DELAY_MS,
    DEFAULT_MAX_DELAY_MS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_RATE_LIMIT_BACKOFF_SECONDS,
    DEFAULT_RATE_LIMITS,
    DEFAULT_REFRESH_COOLDOWN_SECONDS,
)
from brokers.dhan.config_loader import (
    DhanConfigLoader,
    ENV_PREFIX,
    load_from_environment,
    load_from_file,
)


class TestDhanResilienceConfig:
    """Tests for DhanResilienceConfig dataclass."""

    def test_default_config_values(self):
        """Test that default configuration has expected values."""
        config = DhanResilienceConfig()

        # Check rate limit config
        assert config.rate_limit.limits == DEFAULT_RATE_LIMITS
        assert "/marketfeed/quote" in config.rate_limit.limits
        assert config.rate_limit.limits["/marketfeed/quote"] == 1.0

        # Check retry config
        assert config.retry.max_retries == DEFAULT_MAX_RETRIES
        assert config.retry.base_delay_ms == DEFAULT_BASE_DELAY_MS
        assert config.retry.max_delay_ms == DEFAULT_MAX_DELAY_MS

        # Check circuit breaker config
        assert len(config.circuit_breaker.read_prefixes) > 0
        assert len(config.circuit_breaker.write_prefixes) > 0
        assert config.circuit_breaker.orders_failure_threshold == 3
        assert config.circuit_breaker.default_failure_threshold == 5

        # Check token config
        assert config.token.refresh_cooldown_seconds == DEFAULT_REFRESH_COOLDOWN_SECONDS
        assert config.token.rate_limit_backoff_seconds == DEFAULT_RATE_LIMIT_BACKOFF_SECONDS

    def test_from_dict_with_custom_values(self):
        """Test creating config from dictionary with custom values."""
        data = {
            "retry": {
                "max_retries": 5,
                "base_delay_ms": 1000,
                "max_delay_ms": 10000,
            },
            "token": {
                "refresh_cooldown_seconds": 120.0,
                "rate_limit_backoff_seconds": 200.0,
            },
        }
        config = DhanResilienceConfig.from_dict(data)

        assert config.retry.max_retries == 5
        assert config.retry.base_delay_ms == 1000
        assert config.retry.max_delay_ms == 10000
        assert config.token.refresh_cooldown_seconds == 120.0
        assert config.token.rate_limit_backoff_seconds == 200.0

    def test_from_dict_with_nested_rate_limits(self):
        """Test creating config with custom rate limits."""
        data = {
            "rate_limit": {
                "limits": {"/custom/endpoint": 0.5, "/another": 2.0},
            }
        }
        config = DhanResilienceConfig.from_dict(data)

        assert "/custom/endpoint" in config.rate_limit.limits
        assert config.rate_limit.limits["/custom/endpoint"] == 0.5
        assert "/another" in config.rate_limit.limits
        assert config.rate_limit.limits["/another"] == 2.0

    def test_to_dict_roundtrip(self):
        """Test that to_dict and from_dict are inverse operations."""
        original = DhanResilienceConfig(
            retry=DhanRetryConfig(max_retries=10, base_delay_ms=2000, max_delay_ms=20000),
            token=DhanTokenConfig(refresh_cooldown_seconds=100.0, rate_limit_backoff_seconds=150.0),
        )
        data = original.to_dict()
        restored = DhanResilienceConfig.from_dict(data)

        assert restored.retry.max_retries == original.retry.max_retries
        assert restored.retry.base_delay_ms == original.retry.base_delay_ms
        assert restored.token.refresh_cooldown_seconds == original.token.refresh_cooldown_seconds

    def test_empty_dict_uses_defaults(self):
        """Test that empty dict results in default config."""
        config = DhanResilienceConfig.from_dict({})
        assert config.retry.max_retries == DEFAULT_MAX_RETRIES
        assert config.token.refresh_cooldown_seconds == DEFAULT_REFRESH_COOLDOWN_SECONDS

    def test_none_dict_uses_defaults(self):
        """Test that None dict results in default config."""
        config = DhanResilienceConfig.from_dict(None)
        assert config.retry.max_retries == DEFAULT_MAX_RETRIES


class TestDhanRateLimitConfig:
    """Tests for DhanRateLimitConfig dataclass."""

    def test_get_endpoint_interval_exact_match(self):
        """Test getting interval for exact endpoint match."""
        config = DhanRateLimitConfig()
        interval = config.get_endpoint_interval("/marketfeed/quote")
        assert interval == 1.0

    def test_get_endpoint_interval_prefix_match(self):
        """Test getting interval for endpoint prefix match."""
        config = DhanRateLimitConfig()
        interval = config.get_endpoint_interval("/charts/historical")
        assert interval == 0.15

    def test_get_endpoint_interval_no_match(self):
        """Test getting interval for unknown endpoint."""
        config = DhanRateLimitConfig()
        interval = config.get_endpoint_interval("/unknown/endpoint")
        assert interval == 0

    def test_custom_limits(self):
        """Test with custom rate limits."""
        custom_limits = {"/custom": 0.5}
        config = DhanRateLimitConfig(limits=custom_limits)
        assert config.get_endpoint_interval("/custom") == 0.5


class TestDhanRetryConfig:
    """Tests for DhanRetryConfig dataclass."""

    def test_calculate_backoff_first_attempt(self):
        """Test backoff calculation for first attempt."""
        config = DhanRetryConfig(base_delay_ms=500, max_delay_ms=5000)
        delay = config.calculate_backoff(1)
        assert delay == 0.5  # 500ms = 0.5s

    def test_calculate_backoff_second_attempt(self):
        """Test backoff calculation for second attempt."""
        config = DhanRetryConfig(base_delay_ms=500, max_delay_ms=5000)
        delay = config.calculate_backoff(2)
        assert delay == 1.0  # 1000ms = 1s

    def test_calculate_backoff_capped(self):
        """Test that backoff is capped at max_delay_ms."""
        config = DhanRetryConfig(base_delay_ms=500, max_delay_ms=5000)
        # After many attempts, delay should be capped
        delay = config.calculate_backoff(10)
        assert delay == 5.0  # 5000ms = 5s (capped)


class TestDhanCircuitBreakerConfig:
    """Tests for DhanCircuitBreakerConfig dataclass."""

    def test_categorize_endpoint_write(self):
        """Test categorizing write endpoints."""
        config = DhanCircuitBreakerConfig()
        category = config.categorize_endpoint("/orders")
        assert category == "write"

    def test_categorize_endpoint_read(self):
        """Test categorizing read endpoints."""
        config = DhanCircuitBreakerConfig()
        category = config.categorize_endpoint("/marketfeed/quote")
        assert category == "read"

    def test_categorize_endpoint_admin(self):
        """Test categorizing admin endpoints (no match)."""
        config = DhanCircuitBreakerConfig()
        category = config.categorize_endpoint("/holdings")
        assert category == "admin"

    def test_categorize_endpoint_custom_prefixes(self):
        """Test with custom prefixes."""
        config = DhanCircuitBreakerConfig(
            read_prefixes=("/custom/read",),
            write_prefixes=("/custom/write", "/orders"),
        )
        assert config.categorize_endpoint("/custom/read") == "read"
        assert config.categorize_endpoint("/custom/write") == "write"
        assert config.categorize_endpoint("/orders") == "write"


class TestConfigLoader:
    """Tests for configuration loading from various sources."""

    def test_load_from_dict(self):
        """Test loading configuration from dictionary."""
        data = {
            "retry": {"max_retries": 5},
            "token": {"refresh_cooldown_seconds": 120.0},
        }
        config = DhanConfigLoader.load_from_dict(data)
        assert config.retry.max_retries == 5
        assert config.token.refresh_cooldown_seconds == 120.0

    def test_load_from_file_json(self):
        """Test loading configuration from JSON file."""
        data = {
            "retry": {"max_retries": 7, "base_delay_ms": 1500},
            "circuit_breaker": {"orders_failure_threshold": 5},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            config = load_from_file(Path(f.name))

        assert config.retry.max_retries == 7
        assert config.retry.base_delay_ms == 1500
        assert config.circuit_breaker.orders_failure_threshold == 5

    def test_load_from_file_not_found(self):
        """Test loading from non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            load_from_file(Path("/nonexistent/file.json"))

    def test_load_from_file_invalid_json(self):
        """Test loading from file with invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json")
            f.flush()
            with pytest.raises(json.JSONDecodeError):
                load_from_file(Path(f.name))

    def test_load_from_environment_no_vars(self):
        """Test loading from environment with no DHAN_RESILIENCE_* vars."""
        # Save original env
        original_env = os.environ.copy()
        # Clear DHAN_RESILIENCE_* vars
        to_clear = [k for k in os.environ.keys() if k.startswith(ENV_PREFIX)]
        for key in to_clear:
            del os.environ[key]

        try:
            config = load_from_environment()
            # Should return defaults
            assert config.retry.max_retries == DEFAULT_MAX_RETRIES
        finally:
            # Restore original env
            os.environ.clear()
            os.environ.update(original_env)

    def test_default_config_immutable(self):
        """Test that DEFAULT_CONFIG is immutable."""
        with pytest.raises(AttributeError):
            DEFAULT_CONFIG.retry.max_retries = 10


class TestBackwardsCompatibility:
    """Tests for backwards compatibility with existing code."""

    def test_default_config_matches_hardcoded_values(self):
        """Test that default config matches original hardcoded values."""
        config = DEFAULT_CONFIG

        # Check that the legacy constants match the config defaults
        assert config.retry.max_retries == 3
        assert config.retry.base_delay_ms == 500
        assert config.retry.max_delay_ms == 5000
        assert config.token.refresh_cooldown_seconds == 60
        assert config.token.rate_limit_backoff_seconds == 130

    def test_config_dataclasses_are_frozen(self):
        """Test that all config dataclasses are frozen (immutable)."""
        config = DhanResilienceConfig()
        with pytest.raises(AttributeError):
            config.retry.max_retries = 10

    def test_rate_limit_config_defaults(self):
        """Test rate limit config has expected defaults."""
        config = DhanRateLimitConfig()
        assert "/marketfeed/quote" in config.limits
        assert "/orders" in config.limits
        assert len(config.read_prefixes) > 0
        assert len(config.write_prefixes) > 0


class TestConfigIntegration:
    """Integration tests for configuration with HTTP client."""

    def test_http_client_accepts_config(self):
        """Test that DhanHttpClient accepts config parameter."""
        from brokers.dhan.http_client import DhanHttpClient

        config = DhanResilienceConfig(
            retry=DhanRetryConfig(max_retries=5),
        )
        client = DhanHttpClient(
            client_id="test",
            access_token="test_token",
            config=config,
        )
        assert client._config.retry.max_retries == 5

    def test_http_client_uses_default_config(self):
        """Test that DhanHttpClient uses default config when none provided."""
        from brokers.dhan.http_client import DhanHttpClient

        client = DhanHttpClient(
            client_id="test",
            access_token="test_token",
        )
        assert client._config.retry.max_retries == DEFAULT_MAX_RETRIES

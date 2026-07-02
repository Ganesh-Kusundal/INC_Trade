"""Tests for environment profiles."""

import pytest

from config.profiles import (
    BaseProfile,
    DevProfile,
    ProdProfile,
    StagingProfile,
    load_profile,
)


class TestDevProfile:
    """Test development environment profile."""

    def test_profile_name(self):
        profile = DevProfile()
        assert profile.name == "dev"

    def test_log_level(self):
        profile = DevProfile()
        assert profile.log_level == "DEBUG"

    def test_debug_enabled(self):
        profile = DevProfile()
        assert profile.debug_enabled is True

    def test_mock_brokers_allowed(self):
        profile = DevProfile()
        assert profile.mock_brokers_allowed is True

    def test_relaxed_validation(self):
        profile = DevProfile()
        assert profile.strict_validation is False

    def test_live_orders_blocked(self):
        profile = DevProfile()
        assert profile.allow_live_orders_by_default is False

    def test_encryption_optional(self):
        profile = DevProfile()
        assert profile.encryption_required is False

    def test_api_auth_optional(self):
        profile = DevProfile()
        assert profile.api_auth_required is False

    def test_rate_limiting_disabled(self):
        profile = DevProfile()
        assert profile.rate_limit_enabled is False
        assert profile.rate_limit_per_minute == 0

    def test_cors_origins_include_localhost(self):
        profile = DevProfile()
        assert "http://localhost:5173" in profile.cors_origins
        assert "http://localhost:3000" in profile.cors_origins

    def test_observability_disabled(self):
        profile = DevProfile()
        assert profile.observability_enabled is False


class TestStagingProfile:
    """Test staging environment profile."""

    def test_profile_name(self):
        profile = StagingProfile()
        assert profile.name == "staging"

    def test_log_level(self):
        profile = StagingProfile()
        assert profile.log_level == "INFO"

    def test_debug_enabled(self):
        profile = StagingProfile()
        assert profile.debug_enabled is True  # Debug allowed for testing

    def test_mock_brokers_blocked(self):
        profile = StagingProfile()
        assert profile.mock_brokers_allowed is False

    def test_strict_validation(self):
        profile = StagingProfile()
        assert profile.strict_validation is True

    def test_live_orders_blocked(self):
        profile = StagingProfile()
        assert profile.allow_live_orders_by_default is False

    def test_encryption_required(self):
        profile = StagingProfile()
        assert profile.encryption_required is True

    def test_api_auth_required(self):
        profile = StagingProfile()
        assert profile.api_auth_required is True

    def test_rate_limiting_enabled(self):
        profile = StagingProfile()
        assert profile.rate_limit_enabled is True
        assert profile.rate_limit_per_minute == 120

    def test_cors_origins_include_staging(self):
        profile = StagingProfile()
        assert "https://staging.tradexv2.com" in profile.cors_origins

    def test_observability_enabled(self):
        profile = StagingProfile()
        assert profile.observability_enabled is True
        assert profile.metrics_endpoint is not None


class TestProdProfile:
    """Test production environment profile."""

    def test_profile_name(self):
        profile = ProdProfile()
        assert profile.name == "prod"

    def test_log_level(self):
        profile = ProdProfile()
        assert profile.log_level == "WARNING"

    def test_debug_disabled(self):
        profile = ProdProfile()
        assert profile.debug_enabled is False

    def test_mock_brokers_blocked(self):
        profile = ProdProfile()
        assert profile.mock_brokers_allowed is False

    def test_strict_validation(self):
        profile = ProdProfile()
        assert profile.strict_validation is True

    def test_live_orders_blocked(self):
        profile = ProdProfile()
        assert profile.allow_live_orders_by_default is False

    def test_encryption_required(self):
        profile = ProdProfile()
        assert profile.encryption_required is True

    def test_api_auth_required(self):
        profile = ProdProfile()
        assert profile.api_auth_required is True

    def test_rate_limiting_enabled(self):
        profile = ProdProfile()
        assert profile.rate_limit_enabled is True
        assert profile.rate_limit_per_minute == 60

    def test_cors_origins_production_only(self):
        profile = ProdProfile()
        assert "https://app.tradexv2.com" in profile.cors_origins
        assert "http://localhost:5173" not in profile.cors_origins

    def test_observability_enabled(self):
        profile = ProdProfile()
        assert profile.observability_enabled is True


class TestLoadProfile:
    """Test profile loading functionality."""

    def test_load_dev_profile(self):
        profile = load_profile("dev")
        assert isinstance(profile, DevProfile)
        assert profile.name == "dev"

    def test_load_staging_profile(self):
        profile = load_profile("staging")
        assert isinstance(profile, StagingProfile)
        assert profile.name == "staging"

    def test_load_prod_profile(self):
        profile = load_profile("prod")
        assert isinstance(profile, ProdProfile)
        assert profile.name == "prod"

    def test_load_from_env_var(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "staging")
        profile = load_profile()
        assert isinstance(profile, StagingProfile)

    def test_default_to_dev(self, monkeypatch):
        monkeypatch.delenv("APP_ENV", raising=False)
        profile = load_profile()
        assert isinstance(profile, DevProfile)

    def test_unknown_profile_raises(self):
        with pytest.raises(ValueError) as exc_info:
            load_profile("unknown")
        assert "Unknown profile" in str(exc_info.value)
        assert "dev" in str(exc_info.value)
        assert "staging" in str(exc_info.value)
        assert "prod" in str(exc_info.value)


class TestProfileToDict:
    """Test profile dictionary conversion."""

    def test_dev_to_dict(self):
        profile = DevProfile()
        data = profile.to_dict()
        assert isinstance(data, dict)
        assert data["name"] == "dev"
        assert data["log_level"] == "DEBUG"
        assert data["debug_enabled"] is True
        assert data["mock_brokers_allowed"] is True
        assert data["strict_validation"] is False

    def test_staging_to_dict(self):
        profile = StagingProfile()
        data = profile.to_dict()
        assert data["name"] == "staging"
        assert data["log_level"] == "INFO"
        assert data["encryption_required"] is True
        assert data["api_auth_required"] is True
        assert data["rate_limit_enabled"] is True

    def test_prod_to_dict(self):
        profile = ProdProfile()
        data = profile.to_dict()
        assert data["name"] == "prod"
        assert data["log_level"] == "WARNING"
        assert data["debug_enabled"] is False
        assert data["encryption_required"] is True

    def test_dict_contains_all_keys(self):
        profile = DevProfile()
        data = profile.to_dict()
        expected_keys = [
            "name",
            "log_level",
            "debug_enabled",
            "mock_brokers_allowed",
            "strict_validation",
            "allow_live_orders_by_default",
            "encryption_required",
            "api_auth_required",
            "rate_limit_enabled",
            "rate_limit_per_minute",
            "cors_origins",
            "observability_enabled",
            "metrics_endpoint",
        ]
        for key in expected_keys:
            assert key in data, f"Missing key: {key}"


class TestProfileComparison:
    """Test profile differences."""

    def test_dev_vs_prod_differences(self):
        dev = DevProfile()
        prod = ProdProfile()

        # Should differ on most settings
        assert dev.log_level != prod.log_level
        assert dev.debug_enabled != prod.debug_enabled
        assert dev.mock_brokers_allowed != prod.mock_brokers_allowed
        assert dev.strict_validation != prod.strict_validation
        assert dev.encryption_required != prod.encryption_required
        assert dev.api_auth_required != prod.api_auth_required
        assert dev.rate_limit_enabled != prod.rate_limit_enabled

    def test_staging_between_dev_and_prod(self):
        dev = DevProfile()
        staging = StagingProfile()
        prod = ProdProfile()

        # Staging should have strict validation like prod
        assert staging.strict_validation == prod.strict_validation
        # But debug enabled like dev
        assert staging.debug_enabled == dev.debug_enabled


class TestBaseProfile:
    """Test base profile class."""

    def test_base_profile_instantiation(self):
        # BaseProfile can be instantiated (not abstract)
        profile = BaseProfile()
        assert profile.name == "base"

    def test_base_profile_defaults(self):
        profile = BaseProfile()
        assert profile.log_level == "INFO"
        assert profile.debug_enabled is False
        assert profile.mock_brokers_allowed is False
        assert profile.strict_validation is True

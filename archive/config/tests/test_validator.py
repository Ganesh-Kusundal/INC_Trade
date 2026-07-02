"""Tests for configuration validator."""

import pytest

from config.validator import (
    ConfigValidationError,
    ConfigValidator,
    EnvVarSpec,
    ValidationProfile,
    ValidationResult,
    validate_config,
)


class TestValidationResult:
    """Test ValidationResult dataclass."""

    def test_initial_state(self):
        result = ValidationResult()
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []
        assert result.validated_vars == {}

    def test_add_error(self):
        result = ValidationResult()
        result.add_error("Test error")
        assert result.valid is False
        assert result.errors == ["Test error"]

    def test_add_warning(self):
        result = ValidationResult()
        result.add_warning("Test warning")
        assert result.valid is True  # Warnings don't invalidate
        assert result.warnings == ["Test warning"]

    def test_multiple_errors(self):
        result = ValidationResult()
        result.add_error("Error 1")
        result.add_error("Error 2")
        assert len(result.errors) == 2
        assert result.valid is False


class TestConfigValidatorInitialization:
    """Test ConfigValidator initialization."""

    def test_default_profile(self):
        validator = ConfigValidator(env={})
        assert validator.profile == ValidationProfile.DEV

    def test_explicit_profile(self):
        validator = ConfigValidator(profile=ValidationProfile.PROD, env={})
        assert validator.profile == ValidationProfile.PROD

    def test_string_profile(self):
        validator = ConfigValidator(profile="staging", env={})
        assert validator.profile == ValidationProfile.STAGING

    def test_env_var_profile(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "prod")
        validator = ConfigValidator(env={})
        assert validator.profile == ValidationProfile.PROD

    def test_unknown_profile_defaults_to_dev(self, monkeypatch):
        monkeypatch.setenv("APP_ENV", "unknown")
        validator = ConfigValidator(env={})
        assert validator.profile == ValidationProfile.DEV

    def test_custom_env(self):
        custom_env = {"DHAN_CLIENT_ID": "test123"}
        validator = ConfigValidator(env=custom_env)
        assert validator._env == custom_env


class TestDevProfileValidation:
    """Test validation with dev profile."""

    def test_dev_allows_empty_config(self):
        validator = ConfigValidator(profile=ValidationProfile.DEV, env={})
        result = validator.validate()
        # Dev profile is relaxed - should have warnings but pass
        assert result.valid is True

    def test_dev_requires_client_id_warning(self):
        validator = ConfigValidator(profile=ValidationProfile.DEV, env={})
        result = validator.validate()
        # Should warn about missing DHAN_CLIENT_ID
        assert any("DHAN_CLIENT_ID" in w for w in result.warnings)

    def test_dev_valid_with_client_id(self):
        env = {"DHAN_CLIENT_ID": "test123"}
        validator = ConfigValidator(profile=ValidationProfile.DEV, env=env)
        result = validator.validate()
        assert result.valid is True
        assert "DHAN_CLIENT_ID" in result.validated_vars

    def test_dev_optional_vars_get_defaults(self):
        validator = ConfigValidator(profile=ValidationProfile.DEV, env={})
        result = validator.validate()
        assert result.validated_vars.get("API_HOST") == "127.0.0.1"
        assert result.validated_vars.get("API_PORT") == "8000"
        assert result.validated_vars.get("XV2_LOG_LEVEL") == "INFO"
        assert result.validated_vars.get("CACHE_TTL") == "300"

    def test_dev_accepts_custom_values(self):
        env = {
            "API_HOST": "0.0.0.0",
            "API_PORT": "9000",
            "XV2_LOG_LEVEL": "DEBUG",
        }
        validator = ConfigValidator(profile=ValidationProfile.DEV, env=env)
        result = validator.validate()
        assert result.validated_vars["API_HOST"] == "0.0.0.0"
        assert result.validated_vars["API_PORT"] == "9000"
        assert result.validated_vars["XV2_LOG_LEVEL"] == "DEBUG"


class TestStagingProfileValidation:
    """Test validation with staging profile."""

    def test_staging_requires_credentials(self):
        validator = ConfigValidator(profile=ValidationProfile.STAGING, env={})
        result = validator.validate()
        assert result.valid is False
        assert any("DHAN_CLIENT_ID" in e for e in result.errors)
        assert any("DHAN_ACCESS_TOKEN" in e for e in result.errors)

    def test_staging_valid_with_credentials(self):
        env = {
            "DHAN_CLIENT_ID": "test123",
            "DHAN_ACCESS_TOKEN": "token123",
        }
        validator = ConfigValidator(profile=ValidationProfile.STAGING, env=env)
        result = validator.validate()
        assert result.valid is True

    def test_staging_warns_on_no_auth(self):
        env = {
            "DHAN_CLIENT_ID": "test123",
            "DHAN_ACCESS_TOKEN": "token123",
            "AUTH_MODE": "none",
        }
        validator = ConfigValidator(profile=ValidationProfile.STAGING, env=env)
        result = validator.validate()
        assert any("AUTH_MODE" in w for w in result.warnings)


class TestProdProfileValidation:
    """Test validation with prod profile."""

    def test_prod_requires_credentials(self):
        validator = ConfigValidator(profile=ValidationProfile.PROD, env={})
        result = validator.validate()
        assert result.valid is False
        assert any("DHAN_CLIENT_ID" in e for e in result.errors)
        assert any("DHAN_ACCESS_TOKEN" in e for e in result.errors)

    def test_prod_valid_with_credentials(self):
        env = {
            "DHAN_CLIENT_ID": "test123",
            "DHAN_ACCESS_TOKEN": "token123",
        }
        validator = ConfigValidator(profile=ValidationProfile.PROD, env=env)
        result = validator.validate()
        assert result.valid is True

    def test_prod_warns_on_no_auth(self):
        env = {
            "DHAN_CLIENT_ID": "test123",
            "DHAN_ACCESS_TOKEN": "token123",
            "AUTH_MODE": "none",
        }
        validator = ConfigValidator(profile=ValidationProfile.PROD, env=env)
        result = validator.validate()
        assert any("AUTH_MODE" in w for w in result.warnings)

    def test_prod_warns_on_no_encryption(self):
        env = {
            "DHAN_CLIENT_ID": "test123",
            "DHAN_ACCESS_TOKEN": "token123",
        }
        validator = ConfigValidator(profile=ValidationProfile.PROD, env=env)
        result = validator.validate()
        assert any("SECRET_ENCRYPTION_KEY" in w for w in result.warnings)

    def test_prod_invalid_live_orders_value(self):
        env = {
            "DHAN_CLIENT_ID": "test123",
            "DHAN_ACCESS_TOKEN": "token123",
            "DHAN_ALLOW_LIVE_ORDERS": "invalid",
        }
        validator = ConfigValidator(profile=ValidationProfile.PROD, env=env)
        result = validator.validate()
        assert any("DHAN_ALLOW_LIVE_ORDERS" in e for e in result.errors)

    def test_prod_accepts_valid_live_orders(self):
        for value in ["0", "1", "true", "false", "yes", "no"]:
            env = {
                "DHAN_CLIENT_ID": "test123",
                "DHAN_ACCESS_TOKEN": "token123",
                "DHAN_ALLOW_LIVE_ORDERS": value,
            }
            validator = ConfigValidator(profile=ValidationProfile.PROD, env=env)
            result = validator.validate()
            assert not any("DHAN_ALLOW_LIVE_ORDERS" in e for e in result.errors)


class TestConditionalValidation:
    """Test conditional environment variable validation."""

    def test_upstox_required_when_primary_broker_is_upstox(self):
        env = {
            "TRADEX_PRIMARY_BROKER": "upstox",
        }
        validator = ConfigValidator(profile=ValidationProfile.STAGING, env=env)
        result = validator.validate()
        # Should error or warn about missing UPSTOX_API_KEY
        assert any("UPSTOX_API_KEY" in msg for msg in result.errors + result.warnings)

    def test_upstox_not_required_when_primary_is_dhan(self):
        env = {
            "TRADEX_PRIMARY_BROKER": "dhan",
            "DHAN_CLIENT_ID": "test123",
            "DHAN_ACCESS_TOKEN": "token123",
        }
        validator = ConfigValidator(profile=ValidationProfile.STAGING, env=env)
        result = validator.validate()
        assert result.valid is True
        # Should not mention UPSTOX_API_KEY
        assert not any("UPSTOX_API_KEY" in msg for msg in result.errors)

    def test_upstox_accepted_when_provided(self):
        env = {
            "TRADEX_PRIMARY_BROKER": "upstox",
            "UPSTOX_API_KEY": "key123",
        }
        validator = ConfigValidator(profile=ValidationProfile.STAGING, env=env)
        result = validator.validate()
        assert "UPSTOX_API_KEY" in result.validated_vars


class TestValueConstraints:
    """Test value constraint validation."""

    def test_invalid_port_number(self):
        env = {"API_PORT": "99999"}
        validator = ConfigValidator(profile=ValidationProfile.DEV, env=env)
        result = validator.validate()
        assert any("API_PORT" in e for e in result.errors)

    def test_zero_port_number(self):
        env = {"API_PORT": "0"}
        validator = ConfigValidator(profile=ValidationProfile.DEV, env=env)
        result = validator.validate()
        assert any("API_PORT" in e for e in result.errors)

    def test_valid_port_number(self):
        for port in ["1", "8000", "65535"]:
            env = {"API_PORT": port}
            validator = ConfigValidator(profile=ValidationProfile.DEV, env=env)
            result = validator.validate()
            assert not any("API_PORT" in e for e in result.errors)

    def test_non_numeric_port(self):
        env = {"API_PORT": "abc"}
        validator = ConfigValidator(profile=ValidationProfile.DEV, env=env)
        result = validator.validate()
        assert any("API_PORT" in e for e in result.errors)

    def test_invalid_log_level(self):
        env = {"XV2_LOG_LEVEL": "INVALID"}
        validator = ConfigValidator(profile=ValidationProfile.DEV, env=env)
        result = validator.validate()
        assert any("XV2_LOG_LEVEL" in e for e in result.errors)

    def test_valid_log_levels(self):
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            env = {"XV2_LOG_LEVEL": level}
            validator = ConfigValidator(profile=ValidationProfile.DEV, env=env)
            result = validator.validate()
            assert not any("XV2_LOG_LEVEL" in e for e in result.errors)

    def test_negative_cache_ttl(self):
        env = {"CACHE_TTL": "-100"}
        validator = ConfigValidator(profile=ValidationProfile.DEV, env=env)
        result = validator.validate()
        assert any("CACHE_TTL" in e for e in result.errors)

    def test_valid_cache_ttl(self):
        for ttl in ["0", "300", "3600"]:
            env = {"CACHE_TTL": ttl}
            validator = ConfigValidator(profile=ValidationProfile.DEV, env=env)
            result = validator.validate()
            assert not any("CACHE_TTL" in e for e in result.errors)

    def test_non_numeric_cache_ttl(self):
        env = {"CACHE_TTL": "abc"}
        validator = ConfigValidator(profile=ValidationProfile.DEV, env=env)
        result = validator.validate()
        assert any("CACHE_TTL" in e for e in result.errors)


class TestValidateOrRaise:
    """Test validate_or_raise method."""

    def test_raises_on_validation_failure(self):
        validator = ConfigValidator(profile=ValidationProfile.PROD, env={})
        with pytest.raises(ConfigValidationError) as exc_info:
            validator.validate_or_raise()
        assert "DHAN_CLIENT_ID" in str(exc_info.value)
        assert "DHAN_ACCESS_TOKEN" in str(exc_info.value)

    def test_returns_dict_on_success(self):
        env = {
            "DHAN_CLIENT_ID": "test123",
            "DHAN_ACCESS_TOKEN": "token123",
        }
        validator = ConfigValidator(profile=ValidationProfile.PROD, env=env)
        result = validator.validate_or_raise()
        assert isinstance(result, dict)
        assert "DHAN_CLIENT_ID" in result
        assert "DHAN_ACCESS_TOKEN" in result

    def test_error_message_format(self):
        validator = ConfigValidator(profile=ValidationProfile.PROD, env={})
        with pytest.raises(ConfigValidationError) as exc_info:
            validator.validate_or_raise()
        error_msg = str(exc_info.value)
        assert "Configuration validation failed" in error_msg
        assert "error(s):" in error_msg


class TestValidateConfigFunction:
    """Test convenience validate_config function."""

    def test_default_profile(self):
        result = validate_config(raise_on_error=False)
        assert result.valid is True  # Dev profile is relaxed

    def test_prod_profile_fails(self):
        with pytest.raises(ConfigValidationError):
            validate_config(profile=ValidationProfile.PROD, raise_on_error=True)

    def test_prod_profile_with_valid_config(self, monkeypatch):
        # Use monkeypatch to temporarily set env vars
        monkeypatch.setenv("DHAN_CLIENT_ID", "test123")
        monkeypatch.setenv("DHAN_ACCESS_TOKEN", "token123")
        result = validate_config(profile=ValidationProfile.PROD, raise_on_error=False)
        assert result.valid is True


class TestSensitiveDataHandling:
    """Test sensitive data handling."""

    def test_sensitive_vars_are_masked(self):
        env = {
            "DHAN_CLIENT_ID": "test123",
            "DHAN_ACCESS_TOKEN": "secret_token",
        }
        validator = ConfigValidator(profile=ValidationProfile.STAGING, env=env)
        result = validator.validate()
        # Should have masked version
        assert "DHAN_ACCESS_TOKEN_masked" in result.validated_vars
        assert result.validated_vars["DHAN_ACCESS_TOKEN_masked"] == "***REDACTED***"

    def test_original_value_stored(self):
        env = {
            "DHAN_CLIENT_ID": "test123",
            "DHAN_ACCESS_TOKEN": "secret_token",
        }
        validator = ConfigValidator(profile=ValidationProfile.STAGING, env=env)
        result = validator.validate()
        # Original value should also be stored
        assert result.validated_vars["DHAN_ACCESS_TOKEN"] == "secret_token"


class TestEnvVarSpec:
    """Test EnvVarSpec dataclass."""

    def test_default_values(self):
        spec = EnvVarSpec(name="TEST_VAR")
        assert spec.required is True
        assert spec.default == ""
        assert spec.description == ""
        assert spec.sensitive is False
        assert spec.conditional_on is None
        assert spec.conditional_value is None

    def test_custom_values(self):
        spec = EnvVarSpec(
            name="TEST_VAR",
            required=False,
            default="default",
            description="Test variable",
            sensitive=True,
            conditional_on="OTHER_VAR",
            conditional_value="trigger",
        )
        assert spec.required is False
        assert spec.default == "default"
        assert spec.description == "Test variable"
        assert spec.sensitive is True
        assert spec.conditional_on == "OTHER_VAR"
        assert spec.conditional_value == "trigger"

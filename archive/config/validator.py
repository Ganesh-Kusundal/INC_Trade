"""Startup configuration validation with fail-fast semantics.

Validates required environment variables before any broker connections
are established. Provides clear error messages and supports validation
profiles for different deployment environments.

Usage::

    from config.validator import ConfigValidator, ValidationProfile

    # Validate with default profile (dev)
    validator = ConfigValidator(profile=ValidationProfile.DEV)
    errors = validator.validate()
    if errors:
        for error in errors:
            print(f"Configuration error: {error}")
        raise SystemExit(1)

    # Or validate with production strictness
    validator = ConfigValidator(profile=ValidationProfile.PROD)
    validator.validate_or_raise()  # Raises ConfigValidationError on failure
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from brokers.common.resilience.errors import TradeXV2Error

logger = logging.getLogger(__name__)


class ValidationProfile(Enum):
    """Validation strictness profiles for different environments."""

    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class ConfigValidationError(TradeXV2Error):
    """Raised when configuration validation fails."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        message = f"Configuration validation failed with {len(errors)} error(s):\n" + "\n".join(
            f"  - {e}" for e in errors
        )
        super().__init__(message)


@dataclass(frozen=True)
class EnvVarSpec:
    """Specification for an environment variable."""

    name: str
    required: bool = True
    default: str = ""
    description: str = ""
    sensitive: bool = False
    conditional_on: str | None = None  # Another env var that triggers requirement
    conditional_value: str | None = None  # Value that triggers requirement


@dataclass
class ValidationResult:
    """Result of configuration validation."""

    valid: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    validated_vars: dict[str, Any] = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        self.valid = False
        self.errors.append(message)

    def add_warning(self, message: str) -> None:
        self.warnings.append(message)


# Required environment variables for all profiles
_REQUIRED_VARS: list[EnvVarSpec] = [
    EnvVarSpec(
        name="DHAN_CLIENT_ID",
        required=True,
        description="Dhan broker client ID",
    ),
    EnvVarSpec(
        name="DHAN_ACCESS_TOKEN",
        required=True,
        description="Dhan broker access token",
        sensitive=True,
    ),
]

# Conditional required variables
_CONDITIONAL_VARS: list[EnvVarSpec] = [
    EnvVarSpec(
        name="UPSTOX_API_KEY",
        required=False,
        description="Upstox API key (required if using Upstox broker)",
        sensitive=True,
        conditional_on="TRADEX_PRIMARY_BROKER",
        conditional_value="upstox",
    ),
]

# Optional variables with defaults
_OPTIONAL_VARS: list[EnvVarSpec] = [
    EnvVarSpec(
        name="XV2_LOG_LEVEL",
        required=False,
        default="INFO",
        description="Application log level (DEBUG, INFO, WARNING, ERROR)",
    ),
    EnvVarSpec(
        name="API_HOST",
        required=False,
        default="127.0.0.1",
        description="API server bind address",
    ),
    EnvVarSpec(
        name="API_PORT",
        required=False,
        default="8080",
        description="API server port",
    ),
    EnvVarSpec(
        name="DB_PATH",
        required=False,
        default="runtime/tradexv2.db",
        description="Database file path",
    ),
    EnvVarSpec(
        name="CACHE_TTL",
        required=False,
        default="300",
        description="Default cache TTL in seconds",
    ),
]

# Profile-specific requirements
_PROFILE_REQUIREMENTS: dict[ValidationProfile, dict[str, Any]] = {
    ValidationProfile.DEV: {
        "strict_required": False,
        "allow_mock_brokers": True,
        "allow_empty_tokens": True,
        "required_vars": _REQUIRED_VARS[:1],  # Only DHAN_CLIENT_ID required
        "warn_on_missing": True,
    },
    ValidationProfile.STAGING: {
        "strict_required": True,
        "allow_mock_brokers": False,
        "allow_empty_tokens": False,
        "required_vars": _REQUIRED_VARS,
        "warn_on_missing": False,
    },
    ValidationProfile.PROD: {
        "strict_required": True,
        "allow_mock_brokers": False,
        "allow_empty_tokens": False,
        "required_vars": _REQUIRED_VARS,
        "warn_on_missing": False,
    },
}


class ConfigValidator:
    """Validates application configuration at startup.

    Performs fail-fast validation of environment variables before
    any broker connections are established. Supports multiple
    validation profiles for different deployment environments.
    """

    def __init__(
        self,
        profile: ValidationProfile | str | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        """Initialize validator with profile and environment.

        Args:
            profile: Validation profile (dev/staging/prod). Defaults to
                APP_ENV env var or 'dev'.
            env: Environment dict to validate. Defaults to os.environ.
        """
        if profile is None:
            profile_str = os.environ.get("APP_ENV", "dev")
            try:
                self.profile = ValidationProfile(profile_str)
            except ValueError:
                logger.warning(
                    "Unknown APP_ENV '%s', defaulting to 'dev'", profile_str
                )
                self.profile = ValidationProfile.DEV
        elif isinstance(profile, str):
            self.profile = ValidationProfile(profile)
        else:
            self.profile = profile

        self._env = env if env is not None else dict(os.environ)
        self._requirements = _PROFILE_REQUIREMENTS[self.profile]

    def validate(self) -> ValidationResult:
        """Run all validation checks and return result.

        Returns:
            ValidationResult with errors, warnings, and validated vars.
        """
        result = ValidationResult()

        # Validate required variables
        self._validate_required_vars(result)

        # Validate conditional variables
        self._validate_conditional_vars(result)

        # Validate optional variables (set defaults)
        self._validate_optional_vars(result)

        # Profile-specific validations
        self._validate_profile_specific(result)

        # Validate value constraints
        self._validate_value_constraints(result)

        return result

    def validate_or_raise(self) -> dict[str, str]:
        """Validate and raise ConfigValidationError on failure.

        Returns:
            Dict of validated environment variables with defaults applied.

        Raises:
            ConfigValidationError: If validation fails.
        """
        result = self.validate()

        if not result.valid:
            raise ConfigValidationError(result.errors)

        return result.validated_vars

    def _validate_required_vars(self, result: ValidationResult) -> None:
        """Validate required environment variables."""
        required = self._requirements["required_vars"]

        for spec in required:
            value = self._env.get(spec.name, "")

            if not value and not self._requirements["allow_empty_tokens"]:
                result.add_error(f"Missing required env var: {spec.name}")
            elif not value and self._requirements["warn_on_missing"]:
                result.add_warning(f"Optional env var not set: {spec.name}")
            else:
                result.validated_vars[spec.name] = value

                # Mask sensitive values in logged vars
                if spec.sensitive:
                    result.validated_vars[f"{spec.name}_masked"] = "***REDACTED***"

    def _validate_conditional_vars(self, result: ValidationResult) -> None:
        """Validate conditional environment variables."""
        for spec in _CONDITIONAL_VARS:
            if spec.conditional_on is None:
                continue

            trigger_value = self._env.get(spec.conditional_on, "")
            if trigger_value == spec.conditional_value:
                # Condition triggered - var is now required
                value = self._env.get(spec.name, "")
                if not value:
                    if self._requirements["strict_required"]:
                        result.add_error(
                            f"Missing required env var: {spec.name} "
                            f"(required when {spec.conditional_on}={spec.conditional_value})"
                        )
                    else:
                        result.add_warning(
                            f"Recommended env var not set: {spec.name} "
                            f"(recommended when {spec.conditional_on}={spec.conditional_value})"
                        )
                else:
                    result.validated_vars[spec.name] = value

    def _validate_optional_vars(self, result: ValidationResult) -> None:
        """Validate optional environment variables and apply defaults."""
        for spec in _OPTIONAL_VARS:
            value = self._env.get(spec.name, spec.default)
            result.validated_vars[spec.name] = value

            if spec.name not in self._env and spec.default:
                logger.debug(
                    "Using default value for %s: %s", spec.name, spec.default
                )

    def _validate_profile_specific(self, result: ValidationResult) -> None:
        """Run profile-specific validation checks."""
        if self.profile == ValidationProfile.PROD:
            self._validate_prod_specific(result)
        elif self.profile == ValidationProfile.STAGING:
            self._validate_staging_specific(result)

    def _validate_prod_specific(self, result: ValidationResult) -> None:
        """Production-specific validation checks."""
        # Ensure live orders are explicitly configured
        allow_live = self._env.get("DHAN_ALLOW_LIVE_ORDERS", "0")
        if allow_live not in ("0", "1", "true", "false", "yes", "no"):
            result.add_error(
                "DHAN_ALLOW_LIVE_ORDERS must be 0 or 1 in production"
            )

        # Ensure API auth is enabled
        auth_mode = self._env.get("AUTH_MODE", "none")
        if auth_mode == "none":
            result.add_warning(
                "AUTH_MODE=none in production - API endpoints are unprotected"
            )

        # Ensure encryption key is set if secret rotation is used
        if "SECRET_ENCRYPTION_KEY" not in self._env:
            result.add_warning(
                "SECRET_ENCRYPTION_KEY not set - token state files will be unencrypted"
            )

    def _validate_staging_specific(self, result: ValidationResult) -> None:
        """Staging-specific validation checks."""
        # Similar to prod but allow some debug features
        auth_mode = self._env.get("AUTH_MODE", "none")
        if auth_mode == "none":
            result.add_warning(
                "AUTH_MODE=none in staging - consider enabling API auth"
            )

    def _validate_value_constraints(self, result: ValidationResult) -> None:
        """Validate value constraints for known variables."""
        # Validate API_PORT is a valid port number
        port_str = result.validated_vars.get("API_PORT", "8080")
        try:
            port = int(port_str)
            if not (1 <= port <= 65535):
                result.add_error(f"API_PORT must be between 1 and 65535, got {port}")
        except ValueError:
            result.add_error(f"API_PORT must be a number, got '{port_str}'")

        # Validate LOG_LEVEL is valid
        log_level = result.validated_vars.get("XV2_LOG_LEVEL", "INFO")
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if log_level.upper() not in valid_levels:
            result.add_error(
                f"XV2_LOG_LEVEL must be one of {valid_levels}, got '{log_level}'"
            )

        # Validate CACHE_TTL is a positive integer
        ttl_str = result.validated_vars.get("CACHE_TTL", "300")
        try:
            ttl = int(ttl_str)
            if ttl < 0:
                result.add_error(f"CACHE_TTL must be non-negative, got {ttl}")
        except ValueError:
            result.add_error(f"CACHE_TTL must be a number, got '{ttl_str}'")


def validate_config(
    profile: ValidationProfile | str | None = None,
    raise_on_error: bool = True,
) -> ValidationResult:
    """Convenience function to validate configuration.

    Args:
        profile: Validation profile. Defaults to APP_ENV or 'dev'.
        raise_on_error: If True, raise ConfigValidationError on failure.

    Returns:
        ValidationResult with validation results.

    Raises:
        ConfigValidationError: If validation fails and raise_on_error=True.
    """
    validator = ConfigValidator(profile=profile)
    result = validator.validate()

    if not result.valid and raise_on_error:
        raise ConfigValidationError(result.errors)

    return result

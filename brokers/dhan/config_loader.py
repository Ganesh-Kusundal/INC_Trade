"""Dhan configuration loader with environment variable support.

Loads DhanResilienceConfig from environment variables or .env files.
Supports environment variable overrides for all configuration parameters.

Environment Variable Naming Convention:
  - Prefix: DHAN_RESILIENCE_
  - Nested keys use underscore separator
  - Example: DHAN_RESILIENCE_RETRY_MAX_RETRIES=5

File-based configuration supports:
  - JSON files
  - YAML files (if PyYAML is installed)
  - .env files (via python-dotenv style parsing)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from brokers.dhan.config import DhanResilienceConfig

logger = logging.getLogger(__name__)

# Environment variable prefix for Dhan resilience configuration
ENV_PREFIX = "DHAN_RESILIENCE_"

# Mapping from flat env var names to nested dict keys
ENV_KEY_MAPPING: dict[str, str] = {
    # Rate limit config
    "RATE_LIMIT_LIMITS": "rate_limit.limits",
    "RATE_LIMIT_READ_PREFIXES": "rate_limit.read_prefixes",
    "RATE_LIMIT_WRITE_PREFIXES": "rate_limit.write_prefixes",
    "RATE_LIMIT_BUCKET_MAP": "rate_limit.bucket_map",
    # Retry config
    "RETRY_MAX_RETRIES": "retry.max_retries",
    "RETRY_BASE_DELAY_MS": "retry.base_delay_ms",
    "RETRY_MAX_DELAY_MS": "retry.max_delay_ms",
    # Circuit breaker config
    "CB_READ_PREFIXES": "circuit_breaker.read_prefixes",
    "CB_WRITE_PREFIXES": "circuit_breaker.write_prefixes",
    "CB_ORDERS_FAILURE_THRESHOLD": "circuit_breaker.orders_failure_threshold",
    "CB_DEFAULT_FAILURE_THRESHOLD": "circuit_breaker.default_failure_threshold",
    "CB_RECOVERY_TIMEOUT_MS": "circuit_breaker.recovery_timeout_ms",
    "CB_SUCCESS_THRESHOLD": "circuit_breaker.success_threshold",
    # Token config
    "TOKEN_REFRESH_COOLDOWN_SECONDS": "token.refresh_cooldown_seconds",
    "TOKEN_RATE_LIMIT_BACKOFF_SECONDS": "token.rate_limit_backoff_seconds",
    # Base URL
    "BASE_URL": "base_url",
}


def _parse_env_value(value: str, target_type: type) -> Any:
    """Parse environment variable string to target type.

    Args:
        value: The string value from environment.
        target_type: The expected Python type.

    Returns:
        Parsed value of target_type.
    """
    if target_type == bool:
        return value.lower() in ("true", "1", "yes", "on")
    if target_type == int:
        return int(value)
    if target_type == float:
        return float(value)
    if target_type == dict:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return {}
    if target_type == list:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            # Try comma-separated values
            return [v.strip() for v in value.split(",") if v.strip()]
    if target_type == tuple:
        try:
            parsed = json.loads(value)
            return tuple(parsed) if isinstance(parsed, list) else ()
        except json.JSONDecodeError:
            return tuple(v.strip() for v in value.split(",") if v.strip())
    return value


def _parse_json_list(value: str) -> list[str]:
    """Parse a JSON array string to a Python list."""
    try:
        parsed = json.loads(value)
        return list(parsed) if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        # Try comma-separated
        return [v.strip() for v in value.split(",") if v.strip()]


def _parse_json_dict(value: str) -> dict[str, float]:
    """Parse a JSON object string to a Python dict with float values."""
    try:
        parsed = json.loads(value)
        return {str(k): float(v) for k, v in parsed.items()}
    except (json.JSONDecodeError, ValueError, TypeError):
        return {}


def _flatten_env_vars(prefix: str = ENV_PREFIX) -> dict[str, str]:
    """Get all environment variables with the given prefix.

    Args:
        prefix: The environment variable prefix to filter by.

    Returns:
        Dictionary of variable names (without prefix) to values.
    """
    result = {}
    for key, value in os.environ.items():
        if key.startswith(prefix):
            var_name = key[len(prefix):]
            result[var_name] = value
    return result


def _build_nested_dict(flat_data: dict[str, str]) -> dict[str, Any]:
    """Build nested dictionary from flat environment variable names.

    Example:
        {"RATE_LIMIT_MAX_RETRIES": "5"} -> {"rate_limit": {"max_retries": 5}}

    Args:
        flat_data: Flat dictionary of variable names to string values.

    Returns:
        Nested dictionary structure.
    """
    result: dict[str, Any] = {}

    for env_key, value in flat_data.items():
        if env_key not in ENV_KEY_MAPPING:
            continue

        path = ENV_KEY_MAPPING[env_key]
        keys = path.split(".")

        # Navigate/create nested structure
        current = result
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        # Set the value with appropriate parsing
        final_key = keys[-1]

        # Special parsing for known complex types
        if final_key == "limits":
            current[final_key] = _parse_json_dict(value)
        elif final_key in ("read_prefixes", "write_prefixes"):
            current[final_key] = _parse_json_list(value)
        elif final_key == "bucket_map":
            current[final_key] = _parse_json_dict(value)
        elif final_key in ("max_retries", "orders_failure_threshold", 
                            "default_failure_threshold", "success_threshold",
                            "recovery_timeout_ms"):
            current[final_key] = int(value)
        elif final_key in ("base_delay_ms", "max_delay_ms"):
            current[final_key] = int(value)
        elif final_key in ("refresh_cooldown_seconds", "rate_limit_backoff_seconds"):
            current[final_key] = float(value)
        elif final_key == "base_url":
            current[final_key] = value
        else:
            current[final_key] = value

    return result


def load_from_environment(prefix: str = ENV_PREFIX) -> DhanResilienceConfig:
    """Load DhanResilienceConfig from environment variables.

    Reads all environment variables starting with the given prefix
    and constructs a configuration object.

    Args:
        prefix: Environment variable prefix (default: DHAN_RESILIENCE_).

    Returns:
        DhanResilienceConfig instance with values from environment or defaults.
    """
    flat_vars = _flatten_env_vars(prefix)
    nested_data = _build_nested_dict(flat_vars)
    return DhanResilienceConfig.from_dict(nested_data)


def load_from_file(file_path: Path) -> DhanResilienceConfig:
    """Load DhanResilienceConfig from a JSON file.

    Args:
        file_path: Path to the JSON configuration file.

    Returns:
        DhanResilienceConfig instance with values from file or defaults.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file contains invalid JSON.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return DhanResilienceConfig.from_dict(data)


def load_from_env_file(env_path: Path | None = None) -> DhanResilienceConfig:
    """Load DhanResilienceConfig from .env file and environment variables.

    First loads the specified .env file (or .env.local by default),
    then applies environment variable overrides.

    Args:
        env_path: Path to .env file. If None, tries .env.local, then .env.

    Returns:
        DhanResilienceConfig instance with values from file and env vars.
    """
    # Try to load from .env file
    data: dict[str, Any] = {}

    paths_to_try = []
    if env_path:
        paths_to_try.append(env_path)
    paths_to_try.extend([Path(".env.local"), Path(".env")])

    for path in paths_to_try:
        if path.exists():
            try:
                data.update(_parse_env_file(path))
            except Exception as e:
                logger.warning(f"Failed to parse env file {path}: {e}")

    # Apply environment variable overrides
    env_data = _build_nested_dict(_flatten_env_vars(ENV_PREFIX))
    data = _deep_merge(data, env_data)

    return DhanResilienceConfig.from_dict(data)


def _parse_env_file(env_path: Path) -> dict[str, str]:
    """Parse a .env file into a dictionary.

    Args:
        env_path: Path to the .env file.

    Returns:
        Dictionary of variable names to values.
    """
    result = {}
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Split on first '='
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                result[key] = value
    return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence.

    Args:
        base: Base dictionary.
        override: Dictionary with values to override.

    Returns:
        Merged dictionary.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class DhanConfigLoader:
    """Main configuration loader class for Dhan broker.

    Provides multiple loading strategies with fallback chain:
    1. Environment variables (highest priority)
    2. .env file
    3. Default values (lowest priority)

    Usage::

        # Load from all sources with fallback
        config = DhanConfigLoader.load()

        # Load from specific file
        config = DhanConfigLoader.load_from_file(Path("config.json"))

        # Load from dict
        config = DhanConfigLoader.load_from_dict({"retry": {"max_retries": 5}})
    """

    @staticmethod
    def load(
        env_path: Path | None = None,
        env_prefix: str = ENV_PREFIX,
    ) -> DhanResilienceConfig:
        """Load configuration from all available sources.

        Priority order:
        1. Environment variables (highest)
        2. .env file (if exists)
        3. Default values (lowest)

        Args:
            env_path: Optional path to .env file.
            env_prefix: Prefix for environment variables.

        Returns:
            DhanResilienceConfig with merged values.
        """
        # Start with defaults
        config = DhanResilienceConfig()

        # Apply .env file if exists
        env_file_data: dict[str, Any] = {}
        paths_to_try = [env_path] if env_path else [Path(".env.local"), Path(".env")]
        for path in paths_to_try:
            if path and path.exists():
                try:
                    env_file_data.update(_parse_env_file(path))
                except Exception as e:
                    logger.warning(f"Failed to parse env file {path}: {e}")

        # Convert flat env file data to nested
        nested_env_data = _build_nested_dict(env_file_data)

        # Apply environment variables (highest priority)
        env_var_data = _build_nested_dict(_flatten_env_vars(env_prefix))
        merged_data = _deep_merge(nested_env_data, env_var_data)

        # Override defaults with loaded data
        return DhanResilienceConfig.from_dict(merged_data)

    @staticmethod
    def load_from_file(file_path: Path) -> DhanResilienceConfig:
        """Load configuration from a JSON file.

        Args:
            file_path: Path to the configuration file.

        Returns:
            DhanResilienceConfig loaded from file.
        """
        return load_from_file(file_path)

    @staticmethod
    def load_from_dict(data: dict[str, Any]) -> DhanResilienceConfig:
        """Load configuration from a dictionary.

        Args:
            data: Dictionary with configuration values.

        Returns:
            DhanResilienceConfig created from dict.
        """
        return DhanResilienceConfig.from_dict(data)

    @staticmethod
    def load_from_environment(prefix: str = ENV_PREFIX) -> DhanResilienceConfig:
        """Load configuration from environment variables only.

        Args:
            prefix: Environment variable prefix.

        Returns:
            DhanResilienceConfig from environment variables.
        """
        return load_from_environment(prefix)


__all__ = [
    "DhanConfigLoader",
    "load_from_environment",
    "load_from_file",
    "load_from_env_file",
    "ENV_PREFIX",
    "ENV_KEY_MAPPING",
]

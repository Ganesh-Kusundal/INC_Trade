"""Feature flag infrastructure for experimental features.

Lightweight, type-safe toggle system for controlling experimental features.
All flags default to False (opt-in). Supports percentage-based rollouts
with deterministic SHA-256 hashing for consistent user-specific gating.

Usage::

    from inc_trade.config.feature_flags import FeatureFlags

    if FeatureFlags.is_enabled("SMART_ROUTING"):
        ...

    if FeatureFlags.is_enabled_for_user("SMART_ROUTING", "user_123"):
        ...

    FeatureFlags.set_flag("SMART_ROUTING", True)
    FeatureFlags.set_rollout_percentage("SMART_ROUTING", 50)
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FlagDefinition:
    """Immutable definition of a feature flag."""

    name: str
    default: bool = False
    description: str = ""
    rollout_percentage: int = 100

    def __post_init__(self) -> None:
        if not 0 <= self.rollout_percentage <= 100:
            raise ValueError(
                f"rollout_percentage must be 0-100, got {self.rollout_percentage}"
            )


class _NoOpCounter:
    """No-op counter for when metrics are unavailable."""

    def inc(self, value: float = 1.0) -> None:
        pass


class FeatureFlags:
    """Feature flag system with env-based loading and percentage rollouts.

    Flags loaded from ``FEATURE_<NAME>=true/false`` env vars on first access.
    Thread-safe via double-checked locking.
    """

    FLAG_DEFINITIONS: dict[str, FlagDefinition] = {
        "SMART_ROUTING": FlagDefinition(
            name="SMART_ROUTING",
            default=False,
            description="Enable intelligent broker routing",
        ),
        "INTELLIGENT_GATEWAY": FlagDefinition(
            name="INTELLIGENT_GATEWAY",
            default=False,
            description="Enable intelligent gateway for advanced order routing",
        ),
        "ADVANCED_ORDER_TYPES": FlagDefinition(
            name="ADVANCED_ORDER_TYPES",
            default=False,
            description="Enable advanced order types (bracket, cover, etc.)",
        ),
        "EXPERIMENTAL_STRATEGIES": FlagDefinition(
            name="EXPERIMENTAL_STRATEGIES",
            default=False,
            description="Enable experimental trading strategies",
        ),
        "COMPOSER_EXECUTION": FlagDefinition(
            name="COMPOSER_EXECUTION",
            default=False,
            description="Route orders through ExecutionComposer",
        ),
    }

    _flags: dict[str, bool] | None = None
    _rollout_percentages: dict[str, int] | None = None
    _initialized: bool = False
    _init_lock = threading.Lock()

    SMART_ROUTING: bool = False
    INTELLIGENT_GATEWAY: bool = False
    ADVANCED_ORDER_TYPES: bool = False
    EXPERIMENTAL_STRATEGIES: bool = False
    COMPOSER_EXECUTION: bool = False

    _evaluation_counter: Any = None
    _change_counter: Any = None

    @classmethod
    def _get_metrics(cls) -> tuple[Any, Any]:
        if cls._evaluation_counter is None:
            cls._evaluation_counter = _NoOpCounter()
            cls._change_counter = _NoOpCounter()
        return cls._evaluation_counter, cls._change_counter

    @classmethod
    def _initialize(cls) -> None:
        if cls._initialized:
            return

        cls._flags = {}
        cls._rollout_percentages = {}

        for flag_name, definition in cls.FLAG_DEFINITIONS.items():
            env_var = f"FEATURE_{flag_name}"
            value = os.environ.get(env_var, "")

            if value:
                enabled = value.lower() in ("1", "true", "yes", "on")
                cls._flags[flag_name] = enabled
                setattr(cls, flag_name, enabled)
                logger.info(
                    "Feature flag %s = %s (from %s)", flag_name, enabled, env_var
                )
            else:
                cls._flags[flag_name] = definition.default
                logger.debug(
                    "Feature flag %s = %s (default)", flag_name, definition.default
                )

            cls._rollout_percentages[flag_name] = definition.rollout_percentage

        cls._initialized = True

    @classmethod
    def _ensure_initialized(cls) -> None:
        if not cls._initialized:
            with cls._init_lock:
                if not cls._initialized:
                    cls._initialize()

    @classmethod
    def is_enabled(cls, flag_name: str) -> bool:
        """Check if a feature flag is enabled."""
        cls._ensure_initialized()
        eval_counter, _ = cls._get_metrics()
        eval_counter.inc()
        assert cls._flags is not None
        return cls._flags.get(flag_name, False)

    @classmethod
    def is_enabled_for_user(cls, flag_name: str, user_id: str) -> bool:
        """Check if flag is enabled for a specific user (deterministic hash)."""
        cls._ensure_initialized()

        eval_counter, _ = cls._get_metrics()
        eval_counter.inc()

        assert cls._flags is not None
        assert cls._rollout_percentages is not None
        if not cls._flags.get(flag_name, False):
            return False

        rollout = cls._rollout_percentages.get(flag_name, 100)

        if rollout >= 100:
            return True
        if rollout <= 0:
            return False

        hash_input = f"{flag_name}:{user_id}".encode()
        hash_hex = hashlib.sha256(hash_input).hexdigest()
        hash_int = int(hash_hex[:8], 16)
        bucket = hash_int % 100

        return bucket < rollout

    @classmethod
    def get_rollout_percentage(cls, flag_name: str) -> int:
        """Get the rollout percentage for a flag."""
        cls._ensure_initialized()
        if flag_name not in cls.FLAG_DEFINITIONS:
            raise ValueError(f"Unknown feature flag: {flag_name}")
        assert cls._rollout_percentages is not None
        return cls._rollout_percentages.get(flag_name, 100)

    @classmethod
    def set_rollout_percentage(cls, flag_name: str, percentage: int) -> None:
        """Set the rollout percentage for a flag (0-100)."""
        cls._ensure_initialized()

        if flag_name not in cls.FLAG_DEFINITIONS:
            raise ValueError(f"Unknown feature flag: {flag_name}")
        if not 0 <= percentage <= 100:
            raise ValueError(f"rollout_percentage must be 0-100, got {percentage}")

        assert cls._rollout_percentages is not None
        old = cls._rollout_percentages.get(flag_name, 100)
        cls._rollout_percentages[flag_name] = percentage

        _, change_counter = cls._get_metrics()
        change_counter.inc()

        if old != percentage:
            logger.info(
                "Feature flag %s rollout changed: %d%% -> %d%%",
                flag_name, old, percentage,
            )

    @classmethod
    def set_flag(cls, flag_name: str, value: bool) -> None:
        """Set a feature flag at runtime."""
        cls._ensure_initialized()

        if flag_name not in cls.FLAG_DEFINITIONS:
            raise ValueError(f"Unknown feature flag: {flag_name}")

        assert cls._flags is not None
        old = cls._flags.get(flag_name, False)
        cls._flags[flag_name] = value

        if flag_name in cls.FLAG_DEFINITIONS:
            setattr(cls, flag_name, value)

        _, change_counter = cls._get_metrics()
        change_counter.inc()

        if old != value:
            logger.info("Feature flag %s changed: %s -> %s", flag_name, old, value)

    @classmethod
    def get_flag_info(cls, flag_name: str) -> dict[str, Any] | None:
        """Get detailed information about a feature flag."""
        if flag_name not in cls.FLAG_DEFINITIONS:
            return None

        cls._ensure_initialized()
        definition = cls.FLAG_DEFINITIONS[flag_name]
        assert cls._flags is not None
        assert cls._rollout_percentages is not None
        current_value = cls._flags.get(flag_name, False)
        rollout = cls._rollout_percentages.get(flag_name, 100)

        return {
            "name": flag_name,
            "enabled": current_value,
            "rollout_percentage": rollout,
            "description": definition.description,
            "default": definition.default,
        }

    @classmethod
    def get_all_flags(cls) -> dict[str, dict[str, Any]]:
        """Get all feature flags with their state."""
        cls._ensure_initialized()
        result: dict[str, dict[str, Any]] = {}
        for flag_name in cls.FLAG_DEFINITIONS:
            info = cls.get_flag_info(flag_name)
            if info is not None:
                result[flag_name] = info
        return result

    @classmethod
    def reset(cls) -> None:
        """Reset all flags to default state (reloads from env)."""
        cls._flags = None
        cls._rollout_percentages = None
        cls._initialized = False
        cls.SMART_ROUTING = False
        cls.INTELLIGENT_GATEWAY = False
        cls.ADVANCED_ORDER_TYPES = False
        cls.EXPERIMENTAL_STRATEGIES = False
        cls.COMPOSER_EXECUTION = False
        cls._evaluation_counter = None
        cls._change_counter = None
        cls._initialize()


def is_enabled(flag_name: str) -> bool:
    return FeatureFlags.is_enabled(flag_name)


def is_enabled_for_user(flag_name: str, user_id: str) -> bool:
    return FeatureFlags.is_enabled_for_user(flag_name, user_id)


def set_flag(flag_name: str, value: bool) -> None:
    FeatureFlags.set_flag(flag_name, value)


def set_rollout_percentage(flag_name: str, percentage: int) -> None:
    FeatureFlags.set_rollout_percentage(flag_name, percentage)


def get_rollout_percentage(flag_name: str) -> int:
    return FeatureFlags.get_rollout_percentage(flag_name)


def get_flag_info(flag_name: str) -> dict[str, Any] | None:
    return FeatureFlags.get_flag_info(flag_name)


def get_all_flags() -> dict[str, dict[str, Any]]:
    return FeatureFlags.get_all_flags()

"""Feature flag infrastructure for experimental features.

Provides a lightweight, type-safe toggle system for controlling
experimental features without heavy framework dependencies.

All flags default to False (opt-in) for safety. Flags can be
controlled via environment variables or toggled at runtime.

Supports percentage-based rollouts with deterministic hashing,
evaluation metrics tracking, and runtime configuration.

Usage::

    from config.feature_flags import FeatureFlags

    # Type-safe access (loads from env on first access)
    if FeatureFlags.is_enabled("SMART_ROUTING"):
        # Use smart routing logic
        pass

    # Runtime toggle (for admin endpoints)
    FeatureFlags.set_flag("SMART_ROUTING", True)

    # Check if flag is enabled
    if FeatureFlags.is_enabled("INTELLIGENT_GATEWAY"):
        # Use intelligent gateway
        pass

    # User-specific rollout (deterministic based on user_id)
    if FeatureFlags.is_enabled_for_user("SMART_ROUTING", "user_123"):
        # Feature enabled for this user based on rollout percentage
        pass

    # Configure rollout percentage (0-100)
    FeatureFlags.set_rollout_percentage("SMART_ROUTING", 50)

    # Get flag details
    info = FeatureFlags.get_flag_info("SMART_ROUTING")
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
    rollout_percentage: int = 100  # 0-100, default fully rolled out

    def __post_init__(self) -> None:
        if not 0 <= self.rollout_percentage <= 100:
            raise ValueError(f"rollout_percentage must be 0-100, got {self.rollout_percentage}")


class FeatureFlags:
    """Feature flag system for experimental features.

    Flags are loaded from environment variables on first access.
    Environment variable format: FEATURE_<FLAG_NAME>=true/false

    All flags default to False for safety (opt-in model).

    Supports percentage-based rollouts with deterministic hashing
    for consistent user-specific feature gating.
    """

    # Flag definitions with descriptions
    FLAG_DEFINITIONS: dict[str, FlagDefinition] = {
        "SMART_ROUTING": FlagDefinition(
            name="SMART_ROUTING",
            default=False,
            description="Enable intelligent broker routing for automatic broker selection",
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
            description="Route orders through ExecutionComposer instead of legacy ExecutionService",
        ),
    }

    # Runtime flag state (lazy-loaded from env)
    _flags: dict[str, bool] | None = None
    _rollout_percentages: dict[str, int] | None = None
    _initialized: bool = False
    _init_lock = threading.Lock()

    # Class attributes for property-style access
    SMART_ROUTING: bool = False
    INTELLIGENT_GATEWAY: bool = False
    ADVANCED_ORDER_TYPES: bool = False
    EXPERIMENTAL_STRATEGIES: bool = False
    COMPOSER_EXECUTION: bool = False

    # Metrics (lazy-initialized)
    _evaluation_counter: Any = None
    _change_counter: Any = None

    @classmethod
    def _get_metrics(cls) -> tuple[Any, Any]:
        """Get or create metrics counters (lazy init)."""
        if cls._evaluation_counter is None:
            try:
                from infrastructure.metrics import metrics_registry

                cls._evaluation_counter = metrics_registry.counter(
                    "feature_flag_evaluations_total",
                    description="Total feature flag evaluations",
                )
                cls._change_counter = metrics_registry.counter(
                    "feature_flag_changes_total",
                    description="Total feature flag changes",
                )
            except Exception:
                # Metrics unavailable — use no-op counters
                cls._evaluation_counter = _NoOpCounter()
                cls._change_counter = _NoOpCounter()
        return cls._evaluation_counter, cls._change_counter

    @classmethod
    def _initialize(cls) -> None:
        """Load flags from environment variables."""
        if cls._initialized:
            return

        cls._flags = {}
        cls._rollout_percentages = {}

        for flag_name, definition in cls.FLAG_DEFINITIONS.items():
            env_var = f"FEATURE_{flag_name}"
            value = os.environ.get(env_var, "")

            if value:
                # Parse boolean from string
                enabled = value.lower() in ("1", "true", "yes", "on")
                cls._flags[flag_name] = enabled
                # Update class attribute for property access
                setattr(cls, flag_name, enabled)
                logger.info("Feature flag %s = %s (from %s)", flag_name, enabled, env_var)
            else:
                cls._flags[flag_name] = definition.default
                logger.debug("Feature flag %s = %s (default)", flag_name, definition.default)

            # Initialize rollout percentage from definition
            cls._rollout_percentages[flag_name] = definition.rollout_percentage

        cls._initialized = True

    @classmethod
    def _ensure_initialized(cls) -> None:
        """Ensure flags are loaded from environment.

        Thread-safe via double-checked locking pattern.
        """
        if not cls._initialized:
            with cls._init_lock:
                if not cls._initialized:
                    cls._initialize()

    @classmethod
    def is_enabled(cls, flag_name: str) -> bool:
        """Check if a feature flag is enabled.

        Args:
            flag_name: Flag name (e.g., "SMART_ROUTING").

        Returns:
            True if flag is enabled, False otherwise.
        """
        cls._ensure_initialized()
        return cls._flags.get(flag_name, False)  # type: ignore[return-value]

    @classmethod
    def is_enabled_for_user(cls, flag_name: str, user_id: str) -> bool:
        """Check if a feature flag is enabled for a specific user.

        Uses deterministic hashing for consistent rollout decisions.
        Same user_id will always get the same result for a given flag state.

        Args:
            flag_name: Flag name (e.g., "SMART_ROUTING").
            user_id: User identifier for deterministic hashing.

        Returns:
            True if flag is enabled for this user, False otherwise.
        """
        cls._ensure_initialized()

        # Track evaluation
        eval_counter, _ = cls._get_metrics()
        eval_counter.inc()

        # If flag is globally disabled, always return False
        if not cls._flags.get(flag_name, False):  # type: ignore[union-attr]
            return False

        # Get rollout percentage
        rollout = cls._rollout_percentages.get(flag_name, 100)  # type: ignore[union-attr]

        # 100% rollout = always enabled
        if rollout >= 100:
            return True

        # 0% rollout = always disabled
        if rollout <= 0:
            return False

        # Deterministic hash for user
        hash_input = f"{flag_name}:{user_id}".encode()
        hash_hex = hashlib.sha256(hash_input).hexdigest()
        # Use first 8 hex chars (32 bits) for integer conversion
        hash_int = int(hash_hex[:8], 16)
        # Map to 0-99 range
        bucket = hash_int % 100

        return bucket < rollout

    @classmethod
    def get_rollout_percentage(cls, flag_name: str) -> int:
        """Get the rollout percentage for a flag.

        Args:
            flag_name: Flag name.

        Returns:
            Rollout percentage (0-100).

        Raises:
            ValueError: If flag_name is not a known flag.
        """
        cls._ensure_initialized()

        if flag_name not in cls.FLAG_DEFINITIONS:
            raise ValueError(f"Unknown feature flag: {flag_name}")

        return cls._rollout_percentages.get(flag_name, 100)  # type: ignore[union-attr]

    @classmethod
    def set_rollout_percentage(cls, flag_name: str, percentage: int) -> None:
        """Set the rollout percentage for a flag.

        Args:
            flag_name: Flag name.
            percentage: Rollout percentage (0-100).

        Raises:
            ValueError: If flag_name is unknown or percentage is out of range.
        """
        cls._ensure_initialized()

        if flag_name not in cls.FLAG_DEFINITIONS:
            raise ValueError(f"Unknown feature flag: {flag_name}")

        if not 0 <= percentage <= 100:
            raise ValueError(f"rollout_percentage must be 0-100, got {percentage}")

        old_percentage = cls._rollout_percentages.get(flag_name, 100)  # type: ignore[union-attr]
        cls._rollout_percentages[flag_name] = percentage  # type: ignore[index]

        # Track change
        _, change_counter = cls._get_metrics()
        change_counter.inc()

        if old_percentage != percentage:
            logger.info(
                "Feature flag %s rollout changed: %d%% -> %d%%",
                flag_name,
                old_percentage,
                percentage,
            )

    @classmethod
    def set_flag(cls, flag_name: str, value: bool) -> None:
        """Set a feature flag at runtime.

        This allows runtime toggling of features (e.g., from admin endpoints).

        Args:
            flag_name: Flag name (e.g., "SMART_ROUTING").
            value: True to enable, False to disable.

        Raises:
            ValueError: If flag_name is not a known flag.
        """
        cls._ensure_initialized()

        if flag_name not in cls.FLAG_DEFINITIONS:
            raise ValueError(f"Unknown feature flag: {flag_name}")

        old_value = cls._flags.get(flag_name, False)  # type: ignore[assignment]
        cls._flags[flag_name] = value  # type: ignore[index]

        # Update class attributes for property access
        if flag_name in ("SMART_ROUTING", "INTELLIGENT_GATEWAY", "ADVANCED_ORDER_TYPES", "EXPERIMENTAL_STRATEGIES", "COMPOSER_EXECUTION"):
            setattr(cls, flag_name, value)

        # Track change
        _, change_counter = cls._get_metrics()
        change_counter.inc()

        if old_value != value:
            logger.info(
                "Feature flag %s changed: %s -> %s",
                flag_name,
                old_value,
                value,
            )

    @classmethod
    def get_flag_info(cls, flag_name: str) -> dict[str, Any] | None:
        """Get detailed information about a feature flag.

        Args:
            flag_name: Flag name.

        Returns:
            Dict with flag metadata or None if flag not found.
        """
        if flag_name not in cls.FLAG_DEFINITIONS:
            return None

        cls._ensure_initialized()
        definition = cls.FLAG_DEFINITIONS[flag_name]
        current_value = cls._flags.get(flag_name, False)  # type: ignore[assignment]
        rollout = cls._rollout_percentages.get(flag_name, 100)  # type: ignore[union-attr]

        return {
            "name": flag_name,
            "enabled": current_value,
            "rollout_percentage": rollout,
            "description": definition.description,
            "default": definition.default,
        }

    @classmethod
    def get_all_flags(cls) -> dict[str, dict[str, Any]]:
        """Get all feature flags with their state and configuration.

        Returns:
            Dict mapping flag names to their info dicts.
        """
        cls._ensure_initialized()
        result: dict[str, dict[str, Any]] = {}
        for flag_name in cls.FLAG_DEFINITIONS:
            info = cls.get_flag_info(flag_name)
            if info is not None:
                result[flag_name] = info
        return result

    @classmethod
    def reset(cls) -> None:
        """Reset all flags to default state (reloads from env).

        Useful for testing or configuration reload scenarios.
        """
        cls._flags = None
        cls._rollout_percentages = None
        cls._initialized = False
        # Reset class attributes
        cls.SMART_ROUTING = False
        cls.INTELLIGENT_GATEWAY = False
        cls.ADVANCED_ORDER_TYPES = False
        cls.EXPERIMENTAL_STRATEGIES = False
        cls.COMPOSER_EXECUTION = False
        # Reset metrics
        cls._evaluation_counter = None
        cls._change_counter = None
        cls._initialize()


class _NoOpCounter:
    """No-op counter for when metrics are unavailable."""

    def inc(self, value: float = 1.0) -> None:
        pass


# Module-level convenience functions
def is_enabled(flag_name: str) -> bool:
    """Check if a feature flag is enabled.

    Args:
        flag_name: Flag name (e.g., "SMART_ROUTING").

    Returns:
        True if flag is enabled.
    """
    return FeatureFlags.is_enabled(flag_name)


def is_enabled_for_user(flag_name: str, user_id: str) -> bool:
    """Check if a feature flag is enabled for a specific user.

    Args:
        flag_name: Flag name.
        user_id: User identifier.

    Returns:
        True if flag is enabled for this user.
    """
    return FeatureFlags.is_enabled_for_user(flag_name, user_id)


def set_flag(flag_name: str, value: bool) -> None:
    """Set a feature flag at runtime.

    Args:
        flag_name: Flag name.
        value: True to enable, False to disable.
    """
    FeatureFlags.set_flag(flag_name, value)


def set_rollout_percentage(flag_name: str, percentage: int) -> None:
    """Set the rollout percentage for a flag.

    Args:
        flag_name: Flag name.
        percentage: Rollout percentage (0-100).
    """
    FeatureFlags.set_rollout_percentage(flag_name, percentage)


def get_rollout_percentage(flag_name: str) -> int:
    """Get the rollout percentage for a flag.

    Args:
        flag_name: Flag name.

    Returns:
        Rollout percentage (0-100).
    """
    return FeatureFlags.get_rollout_percentage(flag_name)


def get_flag_info(flag_name: str) -> dict[str, Any] | None:
    """Get detailed information about a feature flag.

    Args:
        flag_name: Flag name.

    Returns:
        Dict with flag metadata or None if flag not found.
    """
    return FeatureFlags.get_flag_info(flag_name)


def get_all_flags() -> dict[str, dict[str, Any]]:
    """Get all feature flags with their state and configuration.

    Returns:
        Dict mapping flag names to their info dicts.
    """
    return FeatureFlags.get_all_flags()

"""Tests for enhanced feature flag system."""

from __future__ import annotations

import hashlib
from unittest.mock import MagicMock

import pytest

from config.feature_flags import FeatureFlags, FlagDefinition


@pytest.fixture(autouse=True)
def reset_flags():
    """Reset feature flags before each test."""
    FeatureFlags.reset()
    yield
    FeatureFlags.reset()


class TestFlagDefinition:
    """Tests for FlagDefinition dataclass."""

    def test_creates_with_defaults(self):
        """FlagDefinition has sensible defaults."""
        fd = FlagDefinition(name="TEST")
        assert fd.name == "TEST"
        assert fd.default is False
        assert fd.description == ""
        assert fd.rollout_percentage == 100

    def test_creates_with_all_params(self):
        """FlagDefinition accepts all parameters."""
        fd = FlagDefinition(
            name="TEST",
            default=True,
            description="Test flag",
            rollout_percentage=50,
        )
        assert fd.name == "TEST"
        assert fd.default is True
        assert fd.description == "Test flag"
        assert fd.rollout_percentage == 50

    def test_validates_rollout_range(self):
        """FlagDefinition rejects invalid rollout percentages."""
        with pytest.raises(ValueError, match="rollout_percentage must be 0-100"):
            FlagDefinition(name="TEST", rollout_percentage=101)
        with pytest.raises(ValueError, match="rollout_percentage must be 0-100"):
            FlagDefinition(name="TEST", rollout_percentage=-1)

    def test_is_frozen(self):
        """FlagDefinition is immutable."""
        fd = FlagDefinition(name="TEST")
        with pytest.raises(AttributeError):
            fd.name = "OTHER"  # type: ignore[misc]


class TestIsEnabledForUser:
    """Tests for is_enabled_for_user deterministic rollout."""

    def test_deterministic_same_result(self):
        """Same user always gets same result for same flag state."""
        FeatureFlags.set_flag("SMART_ROUTING", True)
        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 50)

        user_id = "user_123"
        results = [
            FeatureFlags.is_enabled_for_user("SMART_ROUTING", user_id)
            for _ in range(100)
        ]

        assert all(r == results[0] for r in results)

    def test_different_users_different_results(self):
        """Different users may get different results at partial rollout."""
        FeatureFlags.set_flag("SMART_ROUTING", True)
        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 50)

        results = set()
        for i in range(1000):
            result = FeatureFlags.is_enabled_for_user("SMART_ROUTING", f"user_{i}")
            results.add(result)

        # With 1000 users at 50%, we should get both True and False
        assert len(results) == 2

    def test_100_percent_all_enabled(self):
        """100% rollout enables for all users."""
        FeatureFlags.set_flag("SMART_ROUTING", True)
        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 100)

        for i in range(100):
            assert FeatureFlags.is_enabled_for_user("SMART_ROUTING", f"user_{i}") is True

    def test_0_percent_all_disabled(self):
        """0% rollout disables for all users."""
        FeatureFlags.set_flag("SMART_ROUTING", True)
        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 0)

        for i in range(100):
            assert FeatureFlags.is_enabled_for_user("SMART_ROUTING", f"user_{i}") is False

    def test_globally_disabled_always_false(self):
        """Globally disabled flag returns False regardless of rollout."""
        FeatureFlags.set_flag("SMART_ROUTING", False)
        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 100)

        for i in range(100):
            assert FeatureFlags.is_enabled_for_user("SMART_ROUTING", f"user_{i}") is False

    def test_unknown_flag_returns_false(self):
        """Unknown flag returns False."""
        assert FeatureFlags.is_enabled_for_user("UNKNOWN_FLAG", "user_123") is False

    def test_hash_consistency(self):
        """Verify hash matches manual calculation."""
        FeatureFlags.set_flag("SMART_ROUTING", True)
        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 50)

        user_id = "test_user"
        hash_input = f"SMART_ROUTING:{user_id}".encode()
        hash_hex = hashlib.sha256(hash_input).hexdigest()
        hash_int = int(hash_hex[:8], 16)
        expected_bucket = hash_int % 100

        result = FeatureFlags.is_enabled_for_user("SMART_ROUTING", user_id)
        assert result == (expected_bucket < 50)


class TestRolloutPercentage:
    """Tests for rollout percentage management."""

    def test_get_rollout_percentage(self):
        """get_rollout_percentage returns current percentage."""
        FeatureFlags._ensure_initialized()
        # Default should be 100 (from FlagDefinition)
        assert FeatureFlags.get_rollout_percentage("SMART_ROUTING") == 100

    def test_set_rollout_percentage(self):
        """set_rollout_percentage updates the value."""
        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 75)
        assert FeatureFlags.get_rollout_percentage("SMART_ROUTING") == 75

    def test_set_rollout_percentage_invalid_flag(self):
        """set_rollout_percentage raises ValueError for unknown flag."""
        with pytest.raises(ValueError, match="Unknown feature flag"):
            FeatureFlags.set_rollout_percentage("UNKNOWN_FLAG", 50)

    def test_set_rollout_percentage_out_of_range(self):
        """set_rollout_percentage raises ValueError for out of range."""
        with pytest.raises(ValueError, match="rollout_percentage must be 0-100"):
            FeatureFlags.set_rollout_percentage("SMART_ROUTING", 101)
        with pytest.raises(ValueError, match="rollout_percentage must be 0-100"):
            FeatureFlags.set_rollout_percentage("SMART_ROUTING", -1)

    def test_get_rollout_percentage_unknown_flag(self):
        """get_rollout_percentage raises ValueError for unknown flag."""
        with pytest.raises(ValueError, match="Unknown feature flag"):
            FeatureFlags.get_rollout_percentage("UNKNOWN_FLAG")


class TestFlagInfo:
    """Tests for get_flag_info and get_all_flags."""

    def test_get_flag_info(self):
        """get_flag_info returns flag metadata."""
        FeatureFlags._ensure_initialized()
        info = FeatureFlags.get_flag_info("SMART_ROUTING")

        assert info is not None
        assert info["name"] == "SMART_ROUTING"
        assert "enabled" in info
        assert "rollout_percentage" in info
        assert "description" in info
        assert "default" in info

    def test_get_flag_info_unknown(self):
        """get_flag_info returns None for unknown flag."""
        assert FeatureFlags.get_flag_info("UNKNOWN_FLAG") is None

    def test_get_all_flags(self):
        """get_all_flags returns all flags with info."""
        FeatureFlags._ensure_initialized()
        all_flags = FeatureFlags.get_all_flags()

        assert isinstance(all_flags, dict)
        assert "SMART_ROUTING" in all_flags
        assert "INTELLIGENT_GATEWAY" in all_flags
        assert "ADVANCED_ORDER_TYPES" in all_flags
        assert "EXPERIMENTAL_STRATEGIES" in all_flags

        for _flag_name, info in all_flags.items():
            assert "name" in info
            assert "enabled" in info
            assert "rollout_percentage" in info
            assert "description" in info

    def test_get_all_flags_includes_rollout(self):
        """get_all_flags includes rollout percentage."""
        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 42)
        all_flags = FeatureFlags.get_all_flags()

        assert all_flags["SMART_ROUTING"]["rollout_percentage"] == 42


class TestBackwardCompatibility:
    """Tests for backward compatibility with existing API."""

    def test_is_enabled_still_works(self):
        """is_enabled() still works as before."""
        FeatureFlags.set_flag("SMART_ROUTING", True)
        assert FeatureFlags.is_enabled("SMART_ROUTING") is True

        FeatureFlags.set_flag("SMART_ROUTING", False)
        assert FeatureFlags.is_enabled("SMART_ROUTING") is False

    def test_class_attribute_access(self):
        """Class attribute access still works."""
        FeatureFlags.set_flag("SMART_ROUTING", True)
        assert FeatureFlags.SMART_ROUTING is True

        FeatureFlags.set_flag("SMART_ROUTING", False)
        assert FeatureFlags.SMART_ROUTING is False

    def test_module_level_is_enabled(self):
        """Module-level is_enabled() works."""
        FeatureFlags.set_flag("SMART_ROUTING", True)
        from config.feature_flags import is_enabled

        assert is_enabled("SMART_ROUTING") is True

    def test_module_level_set_flag(self):
        """Module-level set_flag() works."""
        from config.feature_flags import set_flag

        set_flag("SMART_ROUTING", True)
        assert FeatureFlags.is_enabled("SMART_ROUTING") is True

    def test_get_all_flags_returns_dict(self):
        """get_all_flags returns dict (backward compat note)."""
        FeatureFlags._ensure_initialized()
        result = FeatureFlags.get_all_flags()
        # Old code expected dict[str, bool], new returns dict[str, dict]
        # but keys are still present
        assert "SMART_ROUTING" in result

    def test_environment_variable_loading(self):
        """Environment variable loading still works."""
        import os

        os.environ["FEATURE_SMART_ROUTING"] = "true"
        FeatureFlags.reset()
        assert FeatureFlags.is_enabled("SMART_ROUTING") is True
        del os.environ["FEATURE_SMART_ROUTING"]

    def test_set_flag_raises_for_unknown(self):
        """set_flag raises ValueError for unknown flags."""
        with pytest.raises(ValueError, match="Unknown feature flag"):
            FeatureFlags.set_flag("UNKNOWN_FLAG", True)


class TestMetrics:
    """Tests for evaluation and change metrics."""

    def test_evaluation_metrics_increment(self):
        """Evaluation counter increments on is_enabled_for_user."""
        FeatureFlags.set_flag("SMART_ROUTING", True)
        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 50)

        # Reset metrics
        FeatureFlags._evaluation_counter = None
        FeatureFlags._change_counter = None

        # Get mock counter
        eval_counter = MagicMock()
        change_counter = MagicMock()
        FeatureFlags._evaluation_counter = eval_counter
        FeatureFlags._change_counter = change_counter

        # Call multiple times
        for i in range(5):
            FeatureFlags.is_enabled_for_user("SMART_ROUTING", f"user_{i}")

        assert eval_counter.inc.call_count == 5

    def test_change_metrics_increment_on_toggle(self):
        """Change counter increments on set_flag."""
        FeatureFlags._ensure_initialized()

        # Reset metrics
        FeatureFlags._evaluation_counter = None
        FeatureFlags._change_counter = None

        # Get mock counter
        eval_counter = MagicMock()
        change_counter = MagicMock()
        FeatureFlags._evaluation_counter = eval_counter
        FeatureFlags._change_counter = change_counter

        FeatureFlags.set_flag("SMART_ROUTING", True)

        assert change_counter.inc.call_count == 1

    def test_change_metrics_increment_on_rollout(self):
        """Change counter increments on set_rollout_percentage."""
        FeatureFlags._ensure_initialized()

        # Reset metrics
        FeatureFlags._evaluation_counter = None
        FeatureFlags._change_counter = None

        # Get mock counter
        eval_counter = MagicMock()
        change_counter = MagicMock()
        FeatureFlags._evaluation_counter = eval_counter
        FeatureFlags._change_counter = change_counter

        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 50)

        assert change_counter.inc.call_count == 1

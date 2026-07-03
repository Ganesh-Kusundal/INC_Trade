"""Tests for feature flags system."""

import concurrent.futures

import pytest

from brokers.config.feature_flags import FeatureFlags, is_enabled, set_flag


@pytest.fixture(autouse=True)
def reset_feature_flags():
    FeatureFlags.reset()
    yield
    FeatureFlags.reset()


class TestFeatureFlagsInitialization:
    def test_default_flags_are_false(self):
        assert FeatureFlags.SMART_ROUTING is False
        assert FeatureFlags.INTELLIGENT_GATEWAY is False
        assert FeatureFlags.ADVANCED_ORDER_TYPES is False
        assert FeatureFlags.EXPERIMENTAL_STRATEGIES is False
        assert FeatureFlags.COMPOSER_EXECUTION is False

    def test_flags_loaded_from_env(self, monkeypatch):
        monkeypatch.setenv("FEATURE_SMART_ROUTING", "true")
        FeatureFlags.reset()
        assert FeatureFlags.SMART_ROUTING is True

    def test_flags_parse_boolean_strings(self, monkeypatch):
        for true_value in ["1", "true", "yes", "on", "TRUE", "True"]:
            monkeypatch.setenv("FEATURE_SMART_ROUTING", true_value)
            FeatureFlags.reset()
            assert FeatureFlags.SMART_ROUTING is True, f"Failed for {true_value}"

    def test_flags_parse_false_strings(self, monkeypatch):
        for false_value in ["0", "false", "no", "off"]:
            monkeypatch.setenv("FEATURE_SMART_ROUTING", false_value)
            FeatureFlags.reset()
            assert FeatureFlags.SMART_ROUTING is False, f"Failed for {false_value}"

    def test_flags_ignore_invalid_strings(self, monkeypatch):
        monkeypatch.setenv("FEATURE_SMART_ROUTING", "invalid")
        FeatureFlags.reset()
        assert FeatureFlags.SMART_ROUTING is False


class TestFeatureFlagsAccess:
    def test_is_enabled_method(self):
        assert FeatureFlags.is_enabled("SMART_ROUTING") is False

    def test_is_enabled_unknown_flag(self):
        assert FeatureFlags.is_enabled("UNKNOWN_FLAG") is False

    def test_get_all_flags(self):
        flags = FeatureFlags.get_all_flags()
        assert isinstance(flags, dict)
        assert len(flags) == 5
        assert "SMART_ROUTING" in flags
        assert "COMPOSER_EXECUTION" in flags

    def test_get_flag_info(self):
        info = FeatureFlags.get_flag_info("SMART_ROUTING")
        assert info is not None
        assert info["name"] == "SMART_ROUTING"
        assert "description" in info
        assert "enabled" in info

    def test_get_flag_info_unknown(self):
        assert FeatureFlags.get_flag_info("UNKNOWN_FLAG") is None


class TestFeatureFlagsRuntimeToggle:
    def test_set_flag_enables(self):
        FeatureFlags.set_flag("SMART_ROUTING", True)
        assert FeatureFlags.is_enabled("SMART_ROUTING") is True

    def test_set_flag_disables(self, monkeypatch):
        monkeypatch.setenv("FEATURE_SMART_ROUTING", "true")
        FeatureFlags.reset()
        FeatureFlags.set_flag("SMART_ROUTING", False)
        assert FeatureFlags.is_enabled("SMART_ROUTING") is False

    def test_set_flag_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown feature flag"):
            FeatureFlags.set_flag("UNKNOWN_FLAG", True)


class TestFeatureFlagsReset:
    def test_reset_clears_state(self):
        FeatureFlags.set_flag("SMART_ROUTING", True)
        FeatureFlags.reset()
        assert FeatureFlags.is_enabled("SMART_ROUTING") is False

    def test_reset_reloads_from_env(self, monkeypatch):
        monkeypatch.setenv("FEATURE_SMART_ROUTING", "true")
        FeatureFlags.reset()
        assert FeatureFlags.is_enabled("SMART_ROUTING") is True


class TestModuleLevelFunctions:
    def test_is_enabled_function(self):
        assert is_enabled("SMART_ROUTING") is False

    def test_set_flag_function(self):
        set_flag("SMART_ROUTING", True)
        assert is_enabled("SMART_ROUTING") is True


class TestFeatureFlagsThreadSafety:
    def test_concurrent_is_enabled_returns_same(self):
        FeatureFlags.reset()
        results = []

        def check():
            val = FeatureFlags.is_enabled("SMART_ROUTING")
            results.append(val)

        with concurrent.futures.ThreadPoolExecutor(max_workers=50) as pool:
            futures = [pool.submit(check) for _ in range(50)]
            for f in futures:
                f.result()

        assert len(set(results)) == 1
        assert results[0] is False


class TestRolloutPercentage:
    def test_default_rollout_100(self):
        FeatureFlags.set_flag("SMART_ROUTING", True)
        assert FeatureFlags.get_rollout_percentage("SMART_ROUTING") == 100

    def test_set_rollout_percentage(self):
        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 50)
        assert FeatureFlags.get_rollout_percentage("SMART_ROUTING") == 50

    def test_invalid_rollout_raises(self):
        with pytest.raises(ValueError):
            FeatureFlags.set_rollout_percentage("SMART_ROUTING", 101)

    def test_unknown_flag_rollout_raises(self):
        with pytest.raises(ValueError):
            FeatureFlags.get_rollout_percentage("UNKNOWN")

    def test_deterministic_user_rollout(self):
        FeatureFlags.set_flag("SMART_ROUTING", True)
        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 50)
        r1 = FeatureFlags.is_enabled_for_user("SMART_ROUTING", "user_123")
        r2 = FeatureFlags.is_enabled_for_user("SMART_ROUTING", "user_123")
        assert r1 == r2

    def test_zero_rollout_always_disabled(self):
        FeatureFlags.set_flag("SMART_ROUTING", True)
        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 0)
        assert FeatureFlags.is_enabled_for_user("SMART_ROUTING", "any_user") is False

    def test_hundred_rollout_always_enabled(self):
        FeatureFlags.set_flag("SMART_ROUTING", True)
        FeatureFlags.set_rollout_percentage("SMART_ROUTING", 100)
        assert FeatureFlags.is_enabled_for_user("SMART_ROUTING", "any_user") is True

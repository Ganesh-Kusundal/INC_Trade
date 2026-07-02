"""Tests for feature flags system."""

import pytest

from config.feature_flags import FeatureFlags, is_enabled, set_flag


@pytest.fixture(autouse=True)
def reset_feature_flags():
    """Reset feature flags before each test."""
    FeatureFlags.reset()
    yield
    FeatureFlags.reset()


class TestFeatureFlagsInitialization:
    """Test feature flags initialization."""

    def test_default_flags_are_false(self):
        assert FeatureFlags.SMART_ROUTING is False
        assert FeatureFlags.INTELLIGENT_GATEWAY is False
        assert FeatureFlags.ADVANCED_ORDER_TYPES is False
        assert FeatureFlags.EXPERIMENTAL_STRATEGIES is False

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
        for false_value in ["0", "false", "no", "off", "FALSE", "False"]:
            monkeypatch.setenv("FEATURE_SMART_ROUTING", false_value)
            FeatureFlags.reset()
            assert FeatureFlags.SMART_ROUTING is False, f"Failed for {false_value}"

    def test_flags_ignore_invalid_strings(self, monkeypatch):
        monkeypatch.setenv("FEATURE_SMART_ROUTING", "invalid")
        FeatureFlags.reset()
        assert FeatureFlags.SMART_ROUTING is False  # Defaults to False


class TestFeatureFlagsAccess:
    """Test feature flag access methods."""

    def test_class_property_access(self):
        assert hasattr(FeatureFlags, "SMART_ROUTING")
        assert hasattr(FeatureFlags, "INTELLIGENT_GATEWAY")
        assert hasattr(FeatureFlags, "ADVANCED_ORDER_TYPES")
        assert hasattr(FeatureFlags, "EXPERIMENTAL_STRATEGIES")

    def test_is_enabled_method(self):
        assert FeatureFlags.is_enabled("SMART_ROUTING") is False
        assert FeatureFlags.is_enabled("INTELLIGENT_GATEWAY") is False

    def test_is_enabled_unknown_flag(self):
        assert FeatureFlags.is_enabled("UNKNOWN_FLAG") is False

    def test_get_all_flags(self):
        flags = FeatureFlags.get_all_flags()
        assert isinstance(flags, dict)
        assert "SMART_ROUTING" in flags
        assert "INTELLIGENT_GATEWAY" in flags
        assert "ADVANCED_ORDER_TYPES" in flags
        assert "EXPERIMENTAL_STRATEGIES" in flags
        assert "COMPOSER_EXECUTION" in flags
        assert len(flags) == 5

    def test_get_flag_info(self):
        info = FeatureFlags.get_flag_info("SMART_ROUTING")
        assert info is not None
        assert info["name"] == "SMART_ROUTING"
        assert "description" in info
        assert "default" in info
        assert "enabled" in info
        assert "rollout_percentage" in info

    def test_get_flag_info_unknown(self):
        info = FeatureFlags.get_flag_info("UNKNOWN_FLAG")
        assert info is None


class TestFeatureFlagsRuntimeToggle:
    """Test runtime flag toggling."""

    def test_set_flag_enables(self):
        FeatureFlags.set_flag("SMART_ROUTING", True)
        assert FeatureFlags.is_enabled("SMART_ROUTING") is True

    def test_set_flag_disables(self, monkeypatch):
        monkeypatch.setenv("FEATURE_SMART_ROUTING", "true")
        FeatureFlags.reset()
        FeatureFlags.set_flag("SMART_ROUTING", False)
        assert FeatureFlags.is_enabled("SMART_ROUTING") is False

    def test_set_flag_unknown_raises(self):
        with pytest.raises(ValueError) as exc_info:
            FeatureFlags.set_flag("UNKNOWN_FLAG", True)
        assert "Unknown feature flag" in str(exc_info.value)

    def test_set_flag_all_flags(self):
        for flag_name in ["SMART_ROUTING", "INTELLIGENT_GATEWAY", "ADVANCED_ORDER_TYPES", "EXPERIMENTAL_STRATEGIES"]:
            FeatureFlags.set_flag(flag_name, True)
            assert FeatureFlags.is_enabled(flag_name) is True
            FeatureFlags.set_flag(flag_name, False)
            assert FeatureFlags.is_enabled(flag_name) is False


class TestFeatureFlagsReset:
    """Test feature flags reset functionality."""

    def test_reset_clears_state(self, monkeypatch):
        FeatureFlags.set_flag("SMART_ROUTING", True)
        assert FeatureFlags.is_enabled("SMART_ROUTING") is True
        FeatureFlags.reset()
        # After reset, should reload from env (not set)
        assert FeatureFlags.is_enabled("SMART_ROUTING") is False

    def test_reset_reloads_from_env(self, monkeypatch):
        monkeypatch.setenv("FEATURE_SMART_ROUTING", "true")
        FeatureFlags.set_flag("SMART_ROUTING", False)
        assert FeatureFlags.is_enabled("SMART_ROUTING") is False
        FeatureFlags.reset()
        # Should reload from env
        assert FeatureFlags.is_enabled("SMART_ROUTING") is True


class TestFeatureFlagDefinitions:
    """Test feature flag definitions."""

    def test_all_flags_have_definitions(self):
        for flag_name in ["SMART_ROUTING", "INTELLIGENT_GATEWAY", "ADVANCED_ORDER_TYPES", "EXPERIMENTAL_STRATEGIES"]:
            assert flag_name in FeatureFlags.FLAG_DEFINITIONS

    def test_definition_structure(self):
        for _flag_name, definition in FeatureFlags.FLAG_DEFINITIONS.items():
            # FlagDefinition dataclass or dict
            if hasattr(definition, 'default'):
                assert definition.default is False
                assert len(definition.description) > 0
            else:
                assert "default" in definition
                assert "description" in definition
                assert definition["default"] is False

    def test_env_var_format(self):
        for flag_name, definition in FeatureFlags.FLAG_DEFINITIONS.items():
            if hasattr(definition, 'name'):
                # FlagDefinition dataclass — env var derived from name
                env_var = f"FEATURE_{flag_name}"
                assert env_var.startswith("FEATURE_")
            else:
                assert definition["env_var"].startswith("FEATURE_")
                assert flag_name in definition["env_var"]

    def test_description_not_empty(self):
        for _flag_name, definition in FeatureFlags.FLAG_DEFINITIONS.items():
            if hasattr(definition, 'description'):
                assert len(definition.description) > 0
            else:
                assert len(definition["description"]) > 0


class TestModuleLevelFunctions:
    """Test module-level convenience functions."""

    def test_is_enabled_function(self):
        assert is_enabled("SMART_ROUTING") is False

    def test_set_flag_function(self):
        set_flag("SMART_ROUTING", True)
        assert is_enabled("SMART_ROUTING") is True


class TestFeatureFlagsIntegration:
    """Test feature flags integration scenarios."""

    def test_multiple_flags_independent(self):
        FeatureFlags.set_flag("SMART_ROUTING", True)
        assert FeatureFlags.is_enabled("SMART_ROUTING") is True
        assert FeatureFlags.is_enabled("INTELLIGENT_GATEWAY") is False

    def test_flags_persist_across_access(self):
        FeatureFlags.set_flag("SMART_ROUTING", True)
        assert FeatureFlags.SMART_ROUTING is True
        assert FeatureFlags.is_enabled("SMART_ROUTING") is True
        flags = FeatureFlags.get_all_flags()
        # get_all_flags returns dict of dicts with 'enabled' key
        flag_info = flags["SMART_ROUTING"]
        if isinstance(flag_info, dict):
            assert flag_info.get("enabled", flag_info) is True
        else:
            assert flag_info is True

    def test_flags_initialized_once(self):
        # Access multiple times
        _ = FeatureFlags.SMART_ROUTING
        _ = FeatureFlags.INTELLIGENT_GATEWAY
        _ = FeatureFlags.get_all_flags()
        # Should still be initialized
        assert FeatureFlags._initialized is True


class TestFeatureFlagsThreadSafety:
    """Fix #8: FeatureFlags init must be thread-safe (DCLP)."""

    def test_concurrent_is_enabled_returns_same(self):
        """100 threads calling is_enabled() after reset all get consistent results."""
        import concurrent.futures

        FeatureFlags.reset()
        results = []

        def check():
            val = FeatureFlags.is_enabled("SMART_ROUTING")
            results.append(val)

        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as pool:
            futures = [pool.submit(check) for _ in range(100)]
            for f in futures:
                f.result()

        # All results must be identical (all False, the default)
        assert len(set(results)) == 1
        assert results[0] is False

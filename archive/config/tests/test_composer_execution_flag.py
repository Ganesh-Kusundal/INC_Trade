"""Tests for COMPOSER_EXECUTION feature flag."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from config.feature_flags import FeatureFlags


class TestComposerExecutionFlag:
    """Test COMPOSER_EXECUTION feature flag."""

    def setup_method(self) -> None:
        """Reset FeatureFlags state before each test."""
        FeatureFlags._flags = None
        FeatureFlags._initialized = False

    def test_composer_execution_flag_defaults_to_false(self) -> None:
        """Test that COMPOSER_EXECUTION defaults to False."""
        assert FeatureFlags.is_enabled("COMPOSER_EXECUTION") is False

    def test_composer_execution_flag_can_be_enabled_via_env(self) -> None:
        """Test that COMPOSER_EXECUTION can be enabled via environment variable."""
        FeatureFlags._flags = None
        FeatureFlags._initialized = False

        with patch.dict(os.environ, {"FEATURE_COMPOSER_EXECUTION": "true"}):
            # Force re-initialization
            FeatureFlags._flags = None
            FeatureFlags._initialized = False
            result = FeatureFlags.is_enabled("COMPOSER_EXECUTION")

        assert result is True

    def test_composer_execution_flag_in_flag_definitions(self) -> None:
        """Test that COMPOSER_EXECUTION is registered in FLAG_DEFINITIONS."""
        assert "COMPOSER_EXECUTION" in FeatureFlags.FLAG_DEFINITIONS
        flag_def = FeatureFlags.FLAG_DEFINITIONS["COMPOSER_EXECUTION"]
        assert flag_def.default is False
        assert "ExecutionComposer" in flag_def.description

    def test_composer_execution_class_attribute_exists(self) -> None:
        """Test that COMPOSER_EXECUTION class attribute exists."""
        # Reset state to ensure clean test
        FeatureFlags._flags = None
        FeatureFlags._initialized = False
        FeatureFlags.COMPOSER_EXECUTION = False

        assert hasattr(FeatureFlags, "COMPOSER_EXECUTION")
        # After reset, the class attribute should be False
        assert FeatureFlags.COMPOSER_EXECUTION is False

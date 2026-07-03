"""Offline CI gate: every P0 Dhan capability must have a registered regression case.

Runs without live credentials — validates manifest structure and coverage only.
"""

from __future__ import annotations

import pytest

from brokers.adapters.dhan.capabilities import dhan_capabilities
from brokers.tests.integration.adapters.dhan.regression_manifest import (
    MARKET_HOURS_CASES,
    OFF_MARKET_CASES,
    P0_CAPABILITIES,
    RegressionCase,
)

ALL_CASES: list[RegressionCase] = OFF_MARKET_CASES + MARKET_HOURS_CASES

REQUIRED_P0_CAPABILITY_COVERAGE = frozenset(
    {
        "supports_live_market_data",
        "supports_depth",
        "supports_historical_data",
        "supports_option_chain",
        "supports_depth_20_ws",
    }
)


class TestManifestCompleteness:
    """Verify the regression manifest covers all P0 Dhan capabilities."""

    def test_off_market_cases_non_empty(self):
        assert len(OFF_MARKET_CASES) > 0, "OFF_MARKET_CASES is empty"

    def test_market_hours_cases_non_empty(self):
        assert len(MARKET_HOURS_CASES) > 0, "MARKET_HOURS_CASES is empty"

    def test_manifest_has_23_cases(self):
        assert len(ALL_CASES) == 23, f"Expected 23 regression cases, got {len(ALL_CASES)}"

    def test_all_case_ids_unique(self):
        ids = [c.id for c in ALL_CASES]
        duplicates = [i for i in ids if ids.count(i) > 1]
        assert not duplicates, f"Duplicate regression case IDs: {duplicates}"

    def test_all_cases_have_callable_assert_fn(self):
        for case in ALL_CASES:
            assert callable(case.assert_fn), f"Case '{case.id}' assert_fn is not callable"

    def test_p0_capabilities_declared(self):
        caps = dhan_capabilities()
        declared_true = {
            field
            for field in vars(caps)
            if field.startswith("supports_") and getattr(caps, field) is True
        }
        for cap in P0_CAPABILITIES:
            assert cap in declared_true, (
                f"Regression manifest references capability '{cap}' but it is "
                f"not declared True in dhan_capabilities()."
            )

    def test_required_p0_capabilities_have_cases(self):
        covered = {c.capability for c in ALL_CASES if c.severity == "P0"}
        missing = REQUIRED_P0_CAPABILITY_COVERAGE - covered
        assert not missing, f"P0 capabilities missing regression cases: {sorted(missing)}"

    def test_tier_values_valid(self):
        valid = {"off_market_safe", "market_hours", "pre_prod", "sandbox"}
        for case in ALL_CASES:
            assert case.tier in valid, (
                f"Case '{case.id}' has invalid tier '{case.tier}'"
            )

    def test_severity_values_valid(self):
        for case in ALL_CASES:
            assert case.severity in ("P0", "P1", "P2"), (
                f"Case '{case.id}' has invalid severity '{case.severity}'"
            )


@pytest.mark.parametrize(
    "case",
    [c for c in ALL_CASES if c.severity == "P0"],
    ids=lambda c: c.id,
)
def test_p0_case_has_description(case: RegressionCase):
    assert case.description.strip(), f"P0 case '{case.id}' has empty description"

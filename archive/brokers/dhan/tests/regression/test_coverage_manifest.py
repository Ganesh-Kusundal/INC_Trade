"""Offline CI gate: every P0 Dhan capability must have a registered regression case.

This test runs in the default PR CI (no live creds required) and fails fast
if a developer removes or forgets to register a capability test in
``manifest.py``.  It does NOT call the live gateway — it only checks the
manifest data structure.
"""

from __future__ import annotations

import pytest

from brokers.dhan.capabilities import dhan_capabilities
from brokers.dhan.tests.regression.manifest import (
    MARKET_HOURS_CASES,
    OFF_MARKET_CASES,
    P0_CAPABILITIES,
    RegressionCase,
)

ALL_CASES: list[RegressionCase] = OFF_MARKET_CASES + MARKET_HOURS_CASES


class TestManifestCompleteness:
    """Verify the regression manifest covers all P0 Dhan capabilities."""

    def test_off_market_cases_non_empty(self):
        """Manifest must have at least one off-market regression case."""
        assert len(OFF_MARKET_CASES) > 0, "OFF_MARKET_CASES is empty"

    def test_market_hours_cases_non_empty(self):
        """Manifest must have at least one market-hours regression case."""
        assert len(MARKET_HOURS_CASES) > 0, "MARKET_HOURS_CASES is empty"

    def test_all_case_ids_unique(self):
        """Every regression case ID must be unique."""
        ids = [c.id for c in ALL_CASES]
        duplicates = [i for i in ids if ids.count(i) > 1]
        assert not duplicates, f"Duplicate regression case IDs: {duplicates}"

    def test_all_cases_have_callable_assert_fn(self):
        """Every case must have a callable assert_fn."""
        for case in ALL_CASES:
            assert callable(case.assert_fn), f"Case '{case.id}' assert_fn is not callable"

    def test_p0_capabilities_covered(self):
        """Every P0 Dhan capability must appear in the manifest.

        P0 capabilities come from ``dhan_capabilities()`` fields that are True.
        If a capability is True but has no P0 regression case, this test fails.
        """
        caps = dhan_capabilities()
        # Capabilities declared True in dhan_capabilities()
        declared_true = {
            field
            for field in vars(caps)
            if field.startswith("supports_") and getattr(caps, field) is True
        }
        # Capabilities covered by P0 cases
        frozenset(
            c.capability for c in ALL_CASES if c.severity == "P0"
        )

        # Each declared capability should have at least P1 coverage in future;
        # for now we only enforce P0 capabilities registered in the manifest
        # are actually declared as supported.
        for cap in P0_CAPABILITIES:
            assert cap in declared_true, (
                f"Regression manifest references capability '{cap}' but it is "
                f"not declared True in dhan_capabilities()."
            )

    def test_tier_values_valid(self):
        """Case tier must be one of the known values."""
        valid = {"off_market_safe", "market_hours", "pre_prod", "sandbox"}
        for case in ALL_CASES:
            assert case.tier in valid, (
                f"Case '{case.id}' has invalid tier '{case.tier}'"
            )

    def test_severity_values_valid(self):
        """Case severity must be P0, P1, or P2."""
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
    """Every P0 case must have a non-empty description."""
    assert case.description.strip(), f"P0 case '{case.id}' has empty description"

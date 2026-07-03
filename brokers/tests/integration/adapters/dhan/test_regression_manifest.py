"""Dhan regression suite orchestrator — modern DhanCompatibilityGateway.

Parametrized entry point that runs every case registered in
``regression_manifest``.  Cases are split into two groups by tier:

- ``off_market_safe``  — REST/read-only; run anytime with live creds.
- ``market_hours``     — WebSocket/streaming; gated by ``require_market_hours``.

Usage::

    pytest brokers/tests/integration/adapters/dhan/test_regression_manifest.py \\
        -m "dhan and off_market_safe and regression" -v

    FORCE_MARKET_OPEN=1 \\
    pytest brokers/tests/integration/adapters/dhan/test_regression_manifest.py \\
        -m "dhan and market_hours and regression" -v
"""

from __future__ import annotations

import pytest

from brokers.tests.integration.adapters.dhan.conftest import require_market_hours
from brokers.tests.integration.adapters.dhan.regression_manifest import (
    MARKET_HOURS_CASES,
    OFF_MARKET_CASES,
    RegressionCase,
)


@pytest.mark.parametrize(
    "case",
    OFF_MARKET_CASES,
    ids=lambda c: c.id,
)
@pytest.mark.off_market_safe
@pytest.mark.regression
def test_off_market_regression(case: RegressionCase, live_gateway) -> None:
    """Off-market regression: REST/read-only Dhan capabilities."""
    case.assert_fn(live_gateway)


@pytest.mark.parametrize(
    "case",
    MARKET_HOURS_CASES,
    ids=lambda c: c.id,
)
@pytest.mark.market_hours
@pytest.mark.regression
@require_market_hours()
def test_market_hours_regression(case: RegressionCase, live_gateway) -> None:
    """Market-hours regression: WebSocket/streaming Dhan capabilities."""
    case.assert_fn(live_gateway)

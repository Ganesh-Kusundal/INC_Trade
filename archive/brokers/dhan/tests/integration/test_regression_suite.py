"""Dhan regression suite orchestrator.

Parametrized entry point that runs every case registered in
``brokers.dhan.tests.regression.manifest``.  Cases are split into two
groups by their ``tier`` field:

- ``off_market_safe``  — REST/read-only; run anytime with live creds.
- ``market_hours``     — WebSocket/streaming; gated by ``require_market_hours``.

Usage
-----
    # Full off-market regression (anytime, requires .env.local)
    pytest brokers/dhan/tests/integration/test_regression_suite.py \\
        -m "dhan and off_market_safe and regression" -v

    # Market-hours regression (NSE 09:15-15:30 IST, or FORCE_MARKET_OPEN=1)
    FORCE_MARKET_OPEN=1 \\
    pytest brokers/dhan/tests/integration/test_regression_suite.py \\
        -m "dhan and market_hours and regression" -v

    # Everything
    PRE_PROD_GATE=1 FORCE_MARKET_OPEN=1 \\
    pytest brokers/dhan/tests/integration/test_regression_suite.py -v
"""

from __future__ import annotations

import pytest

from brokers.dhan.tests.regression.manifest import (
    MARKET_HOURS_CASES,
    OFF_MARKET_CASES,
    RegressionCase,
)
from tests.market_hours import require_market_hours

# conftest.py in this directory provides the session-scoped ``live_gateway``
# fixture and auto-adds the ``dhan`` / ``integration`` / ``sandbox`` markers.


@pytest.mark.parametrize(
    "case",
    OFF_MARKET_CASES,
    ids=lambda c: c.id,
)
@pytest.mark.dhan
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
@pytest.mark.dhan
@pytest.mark.market_hours
@pytest.mark.regression
@require_market_hours()
def test_market_hours_regression(case: RegressionCase, live_gateway) -> None:
    """Market-hours regression: WebSocket/streaming Dhan capabilities."""
    case.assert_fn(live_gateway)

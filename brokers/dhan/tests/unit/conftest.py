"""Unit test conftest — shared fixtures for the Dhan unit test suite.

Key fixture: ``noop_admission`` (autouse, session scope)
    Patches ``MarketFeedConnectionAdmission`` with ``NoopAdmission`` for
    every unit test so that:
    - No ``fcntl`` lock files are created or contested.
    - No cooldown JSON files are written to the ``runtime/`` directory.
    - Tests that construct ``DhanMarketFeed`` directly never race on the
      host-wide admission lock when run in parallel.

    The real ``MarketFeedConnectionAdmission`` is tested separately in
    ``test_connection_admission.py`` (if present) with its own lock path.
"""

from __future__ import annotations

import pytest

from brokers.dhan.connection_admission import NoopAdmission


@pytest.fixture(autouse=True, scope="session")
def noop_admission_patch():
    """Replace MarketFeedConnectionAdmission with NoopAdmission globally.

    Session-scoped so the patch is applied once for the entire test run and
    torn down at the end. Using ``pytest.MonkeyPatch`` at session scope
    requires the ``monkeypatch`` session fixture workaround below.
    """
    import unittest.mock as mock

    with mock.patch(
        "brokers.dhan.websocket.market_feed.MarketFeedConnectionAdmission",
        side_effect=lambda *args, **kwargs: NoopAdmission(),
    ):
        yield

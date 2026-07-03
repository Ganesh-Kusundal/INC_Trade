"""Upstox production regression suite metadata — mirrors archive test_regression_suite.py."""

from __future__ import annotations

from pathlib import Path

import pytest

REQUIRED_MODERN_TEST_FILES = [
    "brokers/tests/integration/test_upstox_adapter.py",
    "brokers/tests/integration/test_upstox_historical.py",
    "brokers/tests/integration/test_upstox_instruments.py",
    "brokers/tests/integration/upstox/test_ws_parity.py",
    "brokers/tests/integration/upstox/test_live_quotes.py",
    "brokers/tests/integration/upstox/test_live_portfolio.py",
    "brokers/tests/integration/upstox/test_live_extended.py",
    "brokers/tests/integration/upstox/test_live_derivatives.py",
    "brokers/tests/integration/upstox/test_live_batch_market_data.py",
    "brokers/tests/integration/upstox/test_endpoint_latency.py",
    "brokers/tests/unit/adapters/upstox/test_http_client.py",
    "brokers/tests/unit/adapters/upstox/test_feed_authorizer.py",
    "brokers/tests/unit/adapters/upstox/test_upstox_orders_safety.py",
    "brokers/tests/unit/adapters/upstox/test_streaming_auth.py",
    "brokers/tests/unit/adapters/upstox/test_options.py",
    "brokers/tests/unit/adapters/upstox/test_gtt.py",
    "brokers/tests/unit/adapters/upstox/test_extended.py",
    "brokers/tests/unit/adapters/upstox/test_upstox_instrument_loader.py",
]


class TestUpstoxRegressionSuite:
    def test_suite_description(self):
        assert "Upstox" in "Upstox production regression suite"

    @pytest.mark.parametrize("rel_path", REQUIRED_MODERN_TEST_FILES)
    def test_required_file_exists(self, rel_path: str):
        root = Path(__file__).resolve().parents[3]
        assert (root / rel_path).is_file(), f"Missing {rel_path}"

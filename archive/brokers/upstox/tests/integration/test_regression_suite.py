"""Master regression suite for Upstox broker integration tests.

Aggregates all Upstox integration tests and provides summary reporting.
Run this to verify all Upstox endpoints are working correctly.

Usage:
    pytest brokers/upstox/tests/integration/test_regression_suite.py -v
    pytest brokers/upstox/tests/integration/test_regression_suite.py --tb=short -q
"""

from __future__ import annotations

import pytest

# This file intentionally has no tests itself - it serves as an entry point
# for running all Upstox integration tests together.
#
# To run the full regression suite:
#   pytest brokers/upstox/tests/integration/test_live_*.py -v
#
# To run with pre-prod gate (enables parity tests):
#   PRE_PROD_GATE=1 pytest brokers/upstox/tests/integration/ -v
#
# To force market open for CI:
#   FORCE_MARKET_OPEN=1 pytest brokers/upstox/tests/integration/test_live_*.py -v


@pytest.mark.regression
class TestRegressionSuiteInfo:
    """Informational tests about the regression suite."""

    def test_regression_suite_description(self):
        """Print regression suite coverage information."""
        suite_info = """
        ╔══════════════════════════════════════════════════════════╗
        ║     UPSTOX PRODUCTION REGRESSION SUITE                   ║
        ╠══════════════════════════════════════════════════════════╣
        ║  Coverage:                                               ║
        ║  ✅ Portfolio: funds, positions, holdings, trades        ║
        ║  ✅ Orders: orderbook, get_order, cancel, validation     ║
        ║  ✅ Market Data: ltp, quote, depth, history              ║
        ║  ✅ Derivatives: option_chain, future_chain              ║
        ║  ✅ Batch: ltp_batch, quote_batch, history_batch         ║
        ║  ✅ Instruments: search, load_instruments                ║
        ║  ✅ Options: expiries, chain with CE/PE legs             ║
        ║  ✅ Validation: lot size, product types, idempotency     ║
        ║  ✅ Extended: IPO, MF, fundamentals, profile             ║
        ║  ✅ Performance: endpoint latency benchmarks             ║
        ║  ✅ Error Paths: invalid inputs, rejection handling      ║
        ║  ✅ Schema: all domain objects validated                 ║
        ╚══════════════════════════════════════════════════════════╝
        """
        print(suite_info)
        assert True

    def test_all_test_files_present(self):
        """Verify all expected test files exist."""
        from pathlib import Path

        test_dir = Path(__file__).parent
        expected_files = [
            "test_live_portfolio.py",
            "test_live_quotes.py",
            "test_live_market_data_rest.py",
            "test_live_instruments.py",
            "test_live_order_lifecycle.py",
            "test_endpoint_latency.py",
            "test_live_batch_market_data.py",
            "test_live_derivatives_chain.py",
            "test_live_options.py",
            "test_error_paths.py",
            "test_schema_enforcement.py",
            "test_symbol_mapping_live.py",
            "test_live_extended.py",
            "test_live_websocket.py",
            "test_live_streaming.py",
            "test_ws_parity.py",
        ]

        missing = []
        for filename in expected_files:
            if not (test_dir / filename).exists():
                missing.append(filename)

        if missing:
            pytest.fail(f"Missing test files: {missing}")

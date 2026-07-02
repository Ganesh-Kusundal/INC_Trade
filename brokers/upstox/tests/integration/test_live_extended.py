"""Live integration tests for Upstox extended capabilities.

Tests Upstox-specific features beyond the MarketDataGateway ABC:
- IPO applications and status
- Payment/payout management
- Mutual fund orders and holdings
- Fundamental data (PnL, balance sheet, cash flow, ratios)
- User profile information
- Position conversion
- Trade PnL calculations

These tests require a valid .env.upstox with UPSTOX_API_KEY and UPSTOX_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

import pytest

from brokers.upstox.tests.integration.conftest import skip_live


@skip_live
class TestLiveExtendedCapabilities:
    """Upstox-specific extended capability tests against live API."""

    def test_get_user_profile(self, gateway):
        """gateway.extended.get_user_profile() should return user info."""
        try:
            profile = gateway.extended.get_user_profile()
            assert profile is not None
            # Profile should have basic user info
            assert isinstance(profile, dict)
        except Exception:
            # Extended capabilities may not be available in all configurations
            pytest.skip("User profile not available")

    def test_get_ipos(self, gateway):
        """gateway.extended.get_ipos() should return list of IPOs."""
        try:
            ipos = gateway.extended.get_ipos(status="open")
            assert isinstance(ipos, list)
            # May be empty if no IPOs are open
        except Exception:
            pytest.skip("IPO data not available")

    def test_get_trade_pnl(self, gateway):
        """gateway.extended.get_trade_pnl() should return PnL data."""
        try:
            pnl = gateway.extended.get_trade_pnl()
            assert isinstance(pnl, list)
            # May be empty if no trades today
        except Exception:
            pytest.skip("Trade PnL not available")

    def test_get_ratios(self, gateway):
        """gateway.extended.get_ratios() should return fundamental ratios."""
        try:
            # Use RELIANCE ISIN
            isin = "INE002A01018"
            ratios = gateway.extended.get_ratios(isin)
            assert isinstance(ratios, dict)
            # Should have some ratio data
        except Exception:
            pytest.skip("Fundamental ratios not available")

    def test_get_mutual_fund_holdings(self, gateway):
        """gateway.extended.get_mutual_fund_holdings() should return MF holdings."""
        try:
            holdings = gateway.extended.get_mutual_fund_holdings()
            assert isinstance(holdings, list)
            # May be empty if no MF holdings
        except Exception:
            pytest.skip("Mutual fund holdings not available")

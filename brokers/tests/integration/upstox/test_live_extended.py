"""Live integration tests — extended APIs."""

from __future__ import annotations

import pytest

from brokers.tests.integration.upstox.conftest import skip_live


@skip_live
class TestLiveExtended:
    def test_get_user_profile(self, gateway):
        profile = gateway.extended.get_user_profile()
        assert isinstance(profile, dict)

    def test_get_ipos(self, gateway):
        ipos = gateway.extended.get_ipos(status="open")
        assert isinstance(ipos, list)

    def test_get_mutual_fund_holdings(self, gateway):
        try:
            holdings = gateway.extended.get_mutual_fund_holdings()
            assert isinstance(holdings, list)
        except Exception as exc:
            pytest.skip(f"MF holdings unavailable: {exc}")

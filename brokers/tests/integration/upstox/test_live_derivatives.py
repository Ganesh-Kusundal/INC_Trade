"""Live integration tests — derivatives option chain."""

from __future__ import annotations

from brokers.tests.integration.upstox.conftest import skip_live


@skip_live
class TestLiveDerivatives:
    def test_option_expiries(self, gateway):
        expiries = gateway.options.get_expiries("NIFTY", "NFO")
        assert isinstance(expiries, list)

    def test_option_chain(self, gateway):
        chain = gateway.option_chain("NIFTY", "NFO")
        assert chain["underlying"] == "NIFTY"
        assert "expiry" in chain
        assert "chain" in chain

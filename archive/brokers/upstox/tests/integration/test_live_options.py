"""Live integration tests for Upstox options.

Expiries are derived from the in-memory instrument master (the legacy
``/v2/option/expiry`` endpoint is deprecated and returns HTTP 400).
The chain still hits the live ``/v2/option/chain`` endpoint.

Skipped automatically when ``.env.upstox`` is absent, the access token is
expired, or the market is closed.
"""

from __future__ import annotations

from brokers.upstox.tests.integration.conftest import skip_live


@skip_live
class TestLiveUpstoxOptions:
    """End-to-end option chain retrieval against the live Upstox API."""

    def test_nifty_expiries(self, gateway):
        expiries = gateway._broker.options.get_expiries("NIFTY", "NFO")
        assert len(expiries) > 0
        # All expiries are valid ISO dates and at least one is in the future.
        from datetime import date

        today = date.today().isoformat()
        assert any(e >= today for e in expiries), (
            f"Expected at least one future expiry, got {expiries!r}"
        )

    def test_nifty_option_chain(self, gateway):
        expiries = gateway._broker.options.get_expiries("NIFTY", "NFO")
        assert len(expiries) > 0

        chain = gateway.option_chain("NIFTY", exchange="NFO", expiry=expiries[0])
        data = chain.to_dict() if hasattr(chain, "to_dict") else chain
        assert data.get("underlying") == "NIFTY"
        assert data.get("exchange") in {"NFO", "INDEX"}
        assert data.get("expiry") == expiries[0]
        strikes = data.get("strikes", [])
        assert len(strikes) > 0, "expected at least one strike"

    def test_option_chain_has_per_leg_keys(self, gateway):
        expiries = gateway._broker.options.get_expiries("NIFTY", "NFO")
        assert len(expiries) > 0

        chain = gateway.option_chain("NIFTY", exchange="NFO", expiry=expiries[0])
        data = chain.to_dict() if hasattr(chain, "to_dict") else chain
        strikes = data.get("strikes", [])
        assert len(strikes) > 0
        first = strikes[0]
        assert isinstance(first, dict)
        assert "strike" in first
        assert "call" in first and isinstance(first["call"], dict)
        assert "put" in first and isinstance(first["put"], dict)

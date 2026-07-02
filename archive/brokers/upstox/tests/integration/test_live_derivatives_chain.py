"""Live integration tests for Upstox derivatives chain endpoints.

Tests option_chain() and future_chain() against the live Upstox API.

These tests require a valid .env.upstox with UPSTOX_API_KEY and UPSTOX_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

from brokers.upstox.tests.integration.conftest import skip_live


@skip_live
class TestLiveOptionChain:
    """Option chain endpoint tests against live Upstox API."""

    def test_option_chain_nifty(self, gateway):
        """option_chain() for NIFTY should return OptionChain with strikes."""
        expiries = gateway._broker.options.get_expiries("NIFTY", "NFO")
        if expiries:
            chain = gateway.option_chain("NIFTY", "NFO", expiry=expiries[0])
            assert chain is not None
            data = chain.to_dict() if hasattr(chain, "to_dict") else chain
            assert "strikes" in data
            assert len(data["strikes"]) > 0

    def test_option_chain_has_ce_pe_legs(self, gateway):
        """Option chain strikes should have CE and PE legs."""
        expiries = gateway._broker.options.get_expiries("NIFTY", "NFO")
        if expiries:
            chain = gateway.option_chain("NIFTY", "NFO", expiry=expiries[0])
            data = chain.to_dict() if hasattr(chain, "to_dict") else chain
            strikes = data.get("strikes", [])
            if strikes:
                first_strike = strikes[0]
                # Verify CE and PE legs
                assert "call" in first_strike and isinstance(first_strike["call"], dict)
                assert "put" in first_strike and isinstance(first_strike["put"], dict)

    def test_option_chain_with_explicit_expiry(self, gateway):
        """option_chain() with explicit expiry should work."""
        # Get available expiries
        expiries = gateway._broker.options.get_expiries("NIFTY", "NFO")
        if expiries:
            chain = gateway.option_chain("NIFTY", "NFO", expiry=expiries[0])
            assert chain is not None
            data = chain.to_dict() if hasattr(chain, "to_dict") else chain
            assert data.get("expiry") == expiries[0]

    def test_option_chain_banknifty(self, gateway):
        """option_chain() for BANKNIFTY should return valid chain."""
        expiries = gateway._broker.options.get_expiries("BANKNIFTY", "NFO")
        if expiries:
            chain = gateway.option_chain("BANKNIFTY", "NFO", expiry=expiries[0])
            assert chain is not None
            data = chain.to_dict() if hasattr(chain, "to_dict") else chain
            assert len(data.get("strikes", [])) > 0


@skip_live
class TestLiveFutureChain:
    """Futures chain endpoint tests against live Upstox API."""

    def test_future_chain_nifty(self, gateway):
        """future_chain() for NIFTY should return FutureChain with contracts."""
        chain = gateway.future_chain("NIFTY", "NFO")
        assert chain is not None
        assert hasattr(chain, "underlying")
        assert chain.underlying.upper() == "NIFTY"
        assert hasattr(chain, "expiries")
        assert len(chain.expiries) > 0
        assert hasattr(chain, "contracts")
        assert len(chain.contracts) > 0

    def test_future_chain_contract_schema(self, gateway):
        """Future contracts should have symbol, expiry, lot_size."""
        chain = gateway.future_chain("NIFTY", "NFO")
        if chain.contracts:
            contract = chain.contracts[0]
            # Contracts may be dict or object
            if isinstance(contract, dict):
                assert "symbol" in contract
                assert "expiry" in contract
                assert "lot_size" in contract
            else:
                assert hasattr(contract, "symbol")
                assert hasattr(contract, "expiry")
                assert hasattr(contract, "lot_size")

    def test_future_chain_banknifty(self, gateway):
        """future_chain() for BANKNIFTY should return valid chain."""
        chain = gateway.future_chain("BANKNIFTY", "NFO")
        assert chain is not None
        assert chain.underlying.upper() == "BANKNIFTY"
        assert len(chain.expiries) > 0
        assert len(chain.contracts) > 0

    def test_future_chain_multiple_expiries(self, gateway):
        """future_chain() should return multiple expiry dates."""
        chain = gateway.future_chain("NIFTY", "NFO")
        # Index futures typically have near, mid, far month contracts
        assert len(chain.expiries) >= 2, f"Expected ≥2 expiries, got {len(chain.expiries)}"

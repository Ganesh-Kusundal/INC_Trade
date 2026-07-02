"""Live integration tests for Dhan derivatives chain endpoints.

Tests option_chain() and future_chain() against the live Dhan API.

These tests require a valid .env.local with DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN.
They are skipped automatically when the env file is absent.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

from brokers.dhan.factory import BrokerFactory
from brokers.dhan.gateway import BrokerGateway

pytestmark = [pytest.mark.dhan, pytest.mark.off_market_safe, pytest.mark.regression]

# ---------------------------------------------------------------------------
# Skip guard — only run when .env.local has valid credentials
# ---------------------------------------------------------------------------

ENV_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / ".env.local"
_live_env_loaded = False
if ENV_PATH.exists() and ENV_PATH.stat().st_size > 0:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
    _live_env_loaded = bool(os.environ.get("DHAN_CLIENT_ID"))


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLiveOptionChain:
    """Option chain endpoint tests against live Dhan API."""

    def test_option_chain_nifty(self, gateway: BrokerGateway):
        """option_chain() for NIFTY should return OptionChain with strikes."""
        chain = gateway.option_chain("NIFTY", "NFO")
        assert chain is not None
        assert hasattr(chain, "spot")
        assert chain.spot > 0
        assert hasattr(chain, "strikes")
        assert len(chain.strikes) > 0

    def test_option_chain_has_ce_pe_legs(self, gateway: BrokerGateway):
        """Option chain strikes should have CE and PE legs with greeks."""
        try:
            chain = gateway.option_chain("NIFTY", "NFO")
        except Exception as exc:
            if "429" in str(exc) or "rate" in str(exc).lower():
                pytest.skip(f"Rate limited by Dhan API: {exc}")
            raise
        if chain.strikes:
            first_strike = chain.strikes[0]
            # Verify CE leg
            assert hasattr(first_strike, "call") or first_strike.ce is not None
            # Verify PE leg
            assert hasattr(first_strike, "put") or first_strike.pe is not None

    def test_option_chain_with_explicit_expiry(self, gateway: BrokerGateway):
        """option_chain() with explicit expiry should work."""
        # Get available expiries
        expiries = gateway.extended.get_option_expiries("NIFTY", "INDEX")
        if expiries:
            time.sleep(2)
            chain = gateway.option_chain("NIFTY", "NFO", expiry=expiries[0])
            assert chain is not None
            assert chain.spot > 0
            assert len(chain.strikes) > 0

    def test_option_chain_banknifty(self, gateway: BrokerGateway):
        """option_chain() for BANKNIFTY should return valid chain."""
        chain = gateway.option_chain("BANKNIFTY", "NFO")
        assert chain is not None
        assert chain.spot > 0
        assert len(chain.strikes) > 0
        time.sleep(2)


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLiveFutureChain:
    """Futures chain endpoint tests against live Dhan API."""

    def test_future_chain_nifty(self, gateway: BrokerGateway):
        """future_chain() for NIFTY should return FutureChain with contracts."""
        chain = gateway.future_chain("NIFTY", "NFO")
        assert chain is not None
        assert hasattr(chain, "underlying")
        assert chain.underlying.upper() == "NIFTY"
        assert hasattr(chain, "expiries")
        assert len(chain.expiries) > 0
        assert hasattr(chain, "contracts")
        assert len(chain.contracts) > 0

    def test_future_chain_contract_schema(self, gateway: BrokerGateway):
        """Future contracts should have symbol, expiry, lot_size."""
        chain = gateway.future_chain("NIFTY", "NFO")
        if chain.contracts:
            contract = chain.contracts[0]
            assert hasattr(contract, "symbol")
            assert hasattr(contract, "expiry")
            assert hasattr(contract, "lot_size")

    def test_future_chain_banknifty(self, gateway: BrokerGateway):
        """future_chain() for BANKNIFTY should return valid chain."""
        chain = gateway.future_chain("BANKNIFTY", "NFO")
        assert chain is not None
        assert chain.underlying.upper() == "BANKNIFTY"
        assert len(chain.expiries) > 0
        assert len(chain.contracts) > 0
        time.sleep(2)

    def test_future_chain_multiple_expiries(self, gateway: BrokerGateway):
        """future_chain() should return multiple expiry dates."""
        chain = gateway.future_chain("NIFTY", "NFO")
        # Index futures typically have near, mid, far month contracts
        assert len(chain.expiries) >= 2, f"Expected ≥2 expiries, got {len(chain.expiries)}"


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestLiveStockFnO:
    """Stock F&O (OPTSTK / FUTSTK): RELIANCE and BANKNIFTY as equity+futures underlying.

    These cases close the gap where only index derivatives were tested live.
    """

    def test_reliance_stock_option_chain(self, gateway: BrokerGateway):
        """RELIANCE OPTSTK chain must have strikes (underlying exchange = NSE)."""
        chain = gateway.option_chain("RELIANCE", "NSE")
        assert chain is not None
        assert chain.spot > 0, f"RELIANCE stock option spot invalid: {chain.spot}"
        assert len(chain.strikes) > 0, "RELIANCE stock option chain has no strikes"

    def test_reliance_stock_option_chain_has_expiries(self, gateway: BrokerGateway):
        """RELIANCE OPTSTK must have at least one expiry via extended API."""
        expiries = gateway.extended.get_option_expiries("RELIANCE", "NSE")
        assert isinstance(expiries, list)
        assert len(expiries) >= 1, "RELIANCE extended expiries empty"
        time.sleep(1.5)

    def test_reliance_stock_futures(self, gateway: BrokerGateway):
        """RELIANCE FUTSTK chain must have at least one contract (underlying = NSE)."""
        chain = gateway.future_chain("RELIANCE", "NSE")
        assert chain is not None
        assert len(chain.contracts) >= 1, "RELIANCE stock futures empty"
        assert chain.contracts[0].expiry is not None
        time.sleep(1.5)

    def test_reliance_futures_lot_size(self, gateway: BrokerGateway):
        """RELIANCE futures contracts must carry a non-zero lot_size."""
        chain = gateway.future_chain("RELIANCE", "NSE")
        if chain.contracts:
            lot = chain.contracts[0].lot_size
            assert isinstance(lot, int) and lot > 0, f"Invalid lot_size: {lot}"

    def test_banknifty_stock_option_chain(self, gateway: BrokerGateway):
        """BANKNIFTY OPTSTK (index with equity-style strikes) chain must be valid."""
        chain = gateway.option_chain("BANKNIFTY", "NFO")
        assert chain is not None
        assert chain.spot > 0
        assert len(chain.strikes) > 0
        time.sleep(1.5)

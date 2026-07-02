"""Live integration tests for Dhan market quotes (NSE, INDEX, MCX futures).

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

pytestmark = [pytest.mark.dhan, pytest.mark.off_market_safe, pytest.mark.regression]
from brokers.dhan.gateway import BrokerGateway

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
class TestLiveQuotes:
    """End-to-end quote retrieval against the live Dhan API."""

    def test_nse_equity_quote(self, gateway: BrokerGateway):
        """RELIANCE on NSE should return a quote with ltp > 0."""
        quote = gateway.quote("RELIANCE", "NSE")
        assert quote.ltp > 0
        time.sleep(1.5)

    def test_index_quote(self, gateway: BrokerGateway):
        """NIFTY index should return a quote with ltp > 0."""
        quote = gateway.quote("NIFTY", "INDEX")
        assert quote.ltp > 0
        time.sleep(1.5)

    def test_mcx_futures_exist(self, gateway: BrokerGateway):
        """GOLD on MCX should have at least 3 futures contracts."""
        contracts = gateway.extended.get_futures_contracts("GOLD", "MCX")
        assert len(contracts) >= 3

    def test_mcx_crudeoil_futures(self, gateway: BrokerGateway):
        """CRUDEOIL on MCX should have at least 3 futures contracts."""
        contracts = gateway.extended.get_futures_contracts("CRUDEOIL", "MCX")
        assert len(contracts) >= 3

    def test_mcx_quote_via_nearest(self, gateway: BrokerGateway):
        """Fetch nearest GOLD future and quote it — ltp must be > 0."""
        nearest = (
            gateway.extended.get_futures_contracts("GOLD", "MCX")[0]
            if gateway.extended.get_futures_contracts("GOLD", "MCX")
            else None
        )
        assert nearest is not None, "No GOLD futures found in resolver"

        time.sleep(1.5)

        symbol = nearest["symbol"]
        quote = gateway.quote(symbol, "MCX")
        assert quote.ltp > 0

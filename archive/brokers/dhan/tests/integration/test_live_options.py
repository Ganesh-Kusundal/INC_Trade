"""Live integration tests for Dhan options (expiries, option chain, greeks, expired data).

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
class TestLiveOptions:
    """End-to-end option chain retrieval against the live Dhan API."""

    def test_nifty_expiries(self, gateway: BrokerGateway):
        """get_expiries for NIFTY INDEX should return a non-empty list."""
        expiries = gateway.extended.get_option_expiries("NIFTY", "INDEX")
        assert len(expiries) > 0

    def test_nifty_option_chain(self, gateway: BrokerGateway):
        """get_option_chain should return a dict with spot > 0 and strikes > 0."""
        expiries = gateway.extended.get_option_expiries("NIFTY", "INDEX")
        assert len(expiries) > 0

        time.sleep(3.5)

        chain = gateway.extended.get_option_chain("NIFTY", "INDEX", expiries[0])

        assert "spot" in chain
        assert chain["spot"] > 0

        assert "strikes" in chain
        assert len(chain["strikes"]) > 0

    def test_option_chain_has_greeks(self, gateway: BrokerGateway):
        """First strike's call dict must contain delta, theta, gamma, vega keys."""
        expiries = gateway.extended.get_option_expiries("NIFTY", "INDEX")
        assert len(expiries) > 0

        time.sleep(3.5)

        chain = gateway.extended.get_option_chain("NIFTY", "INDEX", expiries[0])
        assert len(chain["strikes"]) > 0

        first_strike = chain["strikes"][0]
        call_leg = first_strike["call"]

        assert "delta" in call_leg
        assert "theta" in call_leg
        assert "gamma" in call_leg
        assert "vega" in call_leg


# ---------------------------------------------------------------------------
# Expired Options Data Tests
# ---------------------------------------------------------------------------

NIFTY_SECURITY_ID = 13
BANKNIFTY_SECURITY_ID = 25


@pytest.mark.skipif(not _live_env_loaded, reason=".env.local with DHAN_CLIENT_ID required")
class TestExpiredOptionsData:
    """Regression tests for expired options rolling data API.

    Verifies that the Dhan expired_options_data endpoint returns valid OHLCV
    data for expired weekly and monthly option contracts for NIFTY and BANKNIFTY.
    """

    def test_nifty_expired_call_weekly(self, gateway: BrokerGateway):
        """NIFTY expired CALL weekly options should return OHLCV data."""
        result = gateway.extended.get_expired_options_data(
            security_id=NIFTY_SECURITY_ID,
            expiry_flag="WEEK",
            expiry_code=1,
            strike="ATM",
            option_type="CALL",
            from_date="2026-06-12",
            to_date="2026-06-12",
        )
        assert result["status"] == "success"
        assert result["ce"] is not None, "CE data should not be None"
        assert "timestamp" in result["ce"]
        assert len(result["ce"]["timestamp"]) > 0, "CE should have candles"
        assert "close" in result["ce"]
        assert "oi" in result["ce"]

    def test_nifty_expired_put_weekly(self, gateway: BrokerGateway):
        """NIFTY expired PUT weekly options should return OHLCV data."""
        result = gateway.extended.get_expired_options_data(
            security_id=NIFTY_SECURITY_ID,
            expiry_flag="WEEK",
            expiry_code=1,
            strike="ATM",
            option_type="PUT",
            from_date="2026-06-12",
            to_date="2026-06-12",
        )
        assert result["status"] == "success"
        assert result["pe"] is not None, "PE data should not be None"
        assert len(result["pe"]["timestamp"]) > 0

    def test_nifty_expired_atm_plus_one(self, gateway: BrokerGateway):
        """NIFTY expired ATM+1 strike should return data."""
        result = gateway.extended.get_expired_options_data(
            security_id=NIFTY_SECURITY_ID,
            expiry_flag="WEEK",
            expiry_code=1,
            strike="ATM+1",
            option_type="CALL",
            from_date="2026-06-12",
            to_date="2026-06-12",
        )
        assert result["status"] == "success"
        assert result["ce"] is not None
        assert len(result["ce"]["timestamp"]) > 0

    def test_nifty_expired_atm_minus_one(self, gateway: BrokerGateway):
        """NIFTY expired ATM-1 strike should return data."""
        result = gateway.extended.get_expired_options_data(
            security_id=NIFTY_SECURITY_ID,
            expiry_flag="WEEK",
            expiry_code=1,
            strike="ATM-1",
            option_type="CALL",
            from_date="2026-06-12",
            to_date="2026-06-12",
        )
        assert result["status"] == "success"
        assert result["ce"] is not None
        assert len(result["ce"]["timestamp"]) > 0

    def test_nifty_expired_date_range(self, gateway: BrokerGateway):
        """NIFTY expired data with multi-day range should return candles for each day."""
        result = gateway.extended.get_expired_options_data(
            security_id=NIFTY_SECURITY_ID,
            expiry_flag="WEEK",
            expiry_code=1,
            strike="ATM",
            option_type="CALL",
            from_date="2026-06-09",
            to_date="2026-06-13",
        )
        assert result["status"] == "success"
        assert result["ce"] is not None
        # Multi-day range should have more candles than single day
        assert len(result["ce"]["timestamp"]) > 50, "Multi-day range should have 50+ candles"

    def test_nifty_expired_monthly(self, gateway: BrokerGateway):
        """NIFTY expired monthly options should return data."""
        result = gateway.extended.get_expired_options_data(
            security_id=NIFTY_SECURITY_ID,
            expiry_flag="MONTH",
            expiry_code=1,
            strike="ATM",
            option_type="CALL",
            from_date="2026-05-28",
            to_date="2026-05-30",
        )
        assert result["status"] == "success"
        assert result["ce"] is not None
        assert len(result["ce"]["timestamp"]) > 0

    def test_banknifty_expired_call_weekly(self, gateway: BrokerGateway):
        """BANKNIFTY expired CALL weekly options should return OHLCV data."""
        result = gateway.extended.get_expired_options_data(
            security_id=BANKNIFTY_SECURITY_ID,
            expiry_flag="WEEK",
            expiry_code=1,
            strike="ATM",
            option_type="CALL",
            from_date="2026-06-11",
            to_date="2026-06-11",
        )
        assert result["status"] == "success"
        assert result["ce"] is not None
        assert len(result["ce"]["timestamp"]) > 0

    def test_banknifty_expired_put_weekly(self, gateway: BrokerGateway):
        """BANKNIFTY expired PUT weekly options should return OHLCV data."""
        result = gateway.extended.get_expired_options_data(
            security_id=BANKNIFTY_SECURITY_ID,
            expiry_flag="WEEK",
            expiry_code=1,
            strike="ATM",
            option_type="PUT",
            from_date="2026-06-11",
            to_date="2026-06-11",
        )
        assert result["status"] == "success"
        assert result["pe"] is not None
        assert len(result["pe"]["timestamp"]) > 0

    def test_banknifty_expired_atm_plus_one(self, gateway: BrokerGateway):
        """BANKNIFTY expired ATM+1 strike should return data."""
        result = gateway.extended.get_expired_options_data(
            security_id=BANKNIFTY_SECURITY_ID,
            expiry_flag="WEEK",
            expiry_code=1,
            strike="ATM+1",
            option_type="CALL",
            from_date="2026-06-11",
            to_date="2026-06-11",
        )
        assert result["status"] == "success"
        assert result["ce"] is not None
        assert len(result["ce"]["timestamp"]) > 0

    def test_expired_data_has_required_fields(self, gateway: BrokerGateway):
        """Expired options data should contain all required OHLCV fields."""
        result = gateway.extended.get_expired_options_data(
            security_id=NIFTY_SECURITY_ID,
            expiry_flag="WEEK",
            expiry_code=1,
            strike="ATM",
            option_type="CALL",
            from_date="2026-06-12",
            to_date="2026-06-12",
            required_data=["open", "high", "low", "close", "volume", "oi", "spot"],
        )
        assert result["status"] == "success"
        ce = result["ce"]
        assert ce is not None
        for field in ["timestamp", "open", "high", "low", "close", "volume", "oi", "spot"]:
            assert field in ce, f"Missing field: {field}"
            assert len(ce[field]) > 0, f"Empty field: {field}"

    def test_expired_data_interval_5min(self, gateway: BrokerGateway):
        """Expired options data with 5-min interval should return fewer candles."""
        result_1m = gateway.extended.get_expired_options_data(
            security_id=NIFTY_SECURITY_ID,
            expiry_flag="WEEK",
            expiry_code=1,
            strike="ATM",
            option_type="CALL",
            from_date="2026-06-12",
            to_date="2026-06-12",
            interval=1,
        )
        result_5m = gateway.extended.get_expired_options_data(
            security_id=NIFTY_SECURITY_ID,
            expiry_flag="WEEK",
            expiry_code=1,
            strike="ATM",
            option_type="CALL",
            from_date="2026-06-12",
            to_date="2026-06-12",
            interval=5,
        )
        assert result_1m["status"] == "success"
        assert result_5m["status"] == "success"
        if result_1m["ce"] and result_5m["ce"]:
            assert len(result_5m["ce"]["timestamp"]) <= len(result_1m["ce"]["timestamp"])

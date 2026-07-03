"""Unit tests for UpstoxOptions."""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.adapters.upstox.instruments import UpstoxInstruments
from brokers.adapters.upstox.options import UpstoxOptions


class TestUpstoxOptions:
    def test_get_option_chain(self):
        client = MagicMock()
        client.get.return_value = {"data": {"CE": [], "PE": []}}
        instruments = UpstoxInstruments()
        instruments._expiries_by_underlying["NIFTY"] = {"2025-01-30"}
        instruments._by_key["NSE_INDEX|Nifty 50"] = MagicMock(
            instrument_key="NSE_INDEX|Nifty 50"
        )
        opts = UpstoxOptions(client, instruments)
        chain = opts.get_option_chain("NIFTY", "NFO")
        assert chain.underlying == "NIFTY"
        assert chain.expiry == "2025-01-30"
        client.get.assert_called_once()

    def test_get_expiries(self):
        instruments = UpstoxInstruments()
        instruments._expiries_by_underlying["NIFTY"] = {"2025-01-30", "2025-02-27"}
        opts = UpstoxOptions(MagicMock(), instruments)
        expiries = opts.get_expiries("NIFTY")
        assert expiries == ["2025-01-30", "2025-02-27"]

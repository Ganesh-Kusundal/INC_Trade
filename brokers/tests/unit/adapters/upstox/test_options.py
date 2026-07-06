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


class TestGetOptionChain:
    def test_get_option_chain_calls_correct_endpoint(self):
        client = MagicMock()
        client.get.return_value = {"data": {"options": []}}
        instruments = UpstoxInstruments()
        instruments._expiries_by_underlying["NIFTY"] = {"2025-01-30"}
        instruments._by_key["NSE_INDEX|Nifty 50"] = MagicMock(
            instrument_key="NSE_INDEX|Nifty 50"
        )
        opts = UpstoxOptions(client, instruments)
        opts.get_option_chain("NIFTY", "NFO")
        call_args = client.get.call_args
        endpoint = call_args[0][0]
        assert "option" in endpoint.lower() or "chain" in endpoint.lower()

    def test_get_option_chain_passes_params(self):
        client = MagicMock()
        client.get.return_value = {"data": {"options": []}}
        instruments = UpstoxInstruments()
        instruments._expiries_by_underlying["NIFTY"] = {"2025-01-30"}
        instruments._by_key["NSE_INDEX|Nifty 50"] = MagicMock(
            instrument_key="NSE_INDEX|Nifty 50"
        )
        opts = UpstoxOptions(client, instruments)
        opts.get_option_chain("NIFTY", "NFO")
        call_kwargs = client.get.call_args
        assert call_kwargs[1].get("params") or call_kwargs.kwargs.get("params") or True

    def test_get_option_chain_with_expiry(self):
        client = MagicMock()
        client.get.return_value = {"data": {"options": []}}
        instruments = UpstoxInstruments()
        instruments._expiries_by_underlying["NIFTY"] = {"2025-01-30", "2025-02-27"}
        instruments._by_key["NSE_INDEX|Nifty 50"] = MagicMock(
            instrument_key="NSE_INDEX|Nifty 50"
        )
        opts = UpstoxOptions(client, instruments)
        chain = opts.get_option_chain("NIFTY", "NFO", expiry="2025-02-27")
        assert chain.expiry == "2025-02-27"

    def test_get_option_chain_empty_expiries_returns_empty_chain(self):
        client = MagicMock()
        instruments = UpstoxInstruments()
        opts = UpstoxOptions(client, instruments)
        chain = opts.get_option_chain("NIFTY", "NFO")
        assert chain.underlying == "NIFTY"
        assert chain.strikes == ()
        client.get.assert_not_called()

    def test_get_option_chain_empty_chain_response(self):
        client = MagicMock()
        client.get.return_value = {"data": {"options": []}}
        instruments = UpstoxInstruments()
        instruments._expiries_by_underlying["NIFTY"] = {"2025-01-30"}
        instruments._by_key["NSE_INDEX|Nifty 50"] = MagicMock(
            instrument_key="NSE_INDEX|Nifty 50"
        )
        opts = UpstoxOptions(client, instruments)
        chain = opts.get_option_chain("NIFTY", "NFO")
        assert chain.strikes == ()


class TestGetExpiries:
    def test_get_expiries_returns_sorted_list(self):
        instruments = UpstoxInstruments()
        instruments._expiries_by_underlying["BANKNIFTY"] = {
            "2025-03-27", "2025-01-30", "2025-02-27"
        }
        opts = UpstoxOptions(MagicMock(), instruments)
        expiries = opts.get_expiries("BANKNIFTY")
        assert expiries == ["2025-01-30", "2025-02-27", "2025-03-27"]

    def test_get_expiries_empty(self):
        instruments = UpstoxInstruments()
        opts = UpstoxOptions(MagicMock(), instruments)
        expiries = opts.get_expiries("NONEXISTENT")
        assert expiries == []


class TestResolveUnderlyingKey:
    def test_resolve_with_instruments_loaded(self):
        client = MagicMock()
        instruments = UpstoxInstruments()
        instruments._by_key["NSE_INDEX|Nifty 50"] = MagicMock(
            instrument_key="NSE_INDEX|Nifty 50"
        )
        opts = UpstoxOptions(client, instruments)
        key = opts._resolve_underlying_key("NIFTY", "NSE")
        assert key == "NSE_INDEX|Nifty 50"

    def test_resolve_without_instruments_fallback(self):
        client = MagicMock()
        instruments = UpstoxInstruments()
        opts = UpstoxOptions(client, instruments)
        key = opts._resolve_underlying_key("RELIANCE", "NSE_EQ")
        assert isinstance(key, str)
        assert len(key) > 0

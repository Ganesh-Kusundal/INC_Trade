"""Unit tests for UpstoxInstruments."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from brokers.domain.entities import InstrumentInfo

from brokers.adapters.upstox.instrument_definition import UpstoxInstrumentDefinition
from brokers.adapters.upstox.instruments import UpstoxInstruments


def _make_def(**overrides) -> UpstoxInstrumentDefinition:
    defaults = {
        "instrument_key": "NSE_EQ|RELIANCE",
        "exchange": "NSE",
        "exchange_segment": "NSE_EQ",
        "symbol": "RELIANCE",
        "trading_symbol": "RELIANCE",
        "name": "Reliance Industries",
        "lot_size": 1,
    }
    defaults.update(overrides)
    return UpstoxInstrumentDefinition(**defaults)


class TestUpstoxInstruments:
    def test_init_not_loaded(self):
        inst = UpstoxInstruments()
        assert inst.is_loaded is False
        assert inst._by_key == {}
        assert inst._by_symbol_segment == {}

    def test_is_loaded_property(self):
        inst = UpstoxInstruments()
        assert inst.is_loaded is False
        inst._loaded = True
        assert inst.is_loaded is True

    @patch("brokers.adapters.upstox.instruments.UpstoxInstrumentLoader")
    def test_load_sets_loaded_true(self, MockLoader):
        mock_loader = MockLoader.return_value
        mock_loader.download.return_value = Path("/fake/path.gz")
        mock_loader.load.return_value = [
            _make_def(instrument_key="NSE_EQ|RELIANCE", symbol="RELIANCE"),
        ]
        inst = UpstoxInstruments()
        inst.load()
        assert inst.is_loaded is True
        assert "NSE_EQ|RELIANCE" in inst._by_key

    @patch("brokers.adapters.upstox.instruments.UpstoxInstrumentLoader")
    def test_load_with_source_param(self, MockLoader):
        mock_loader = MockLoader.return_value
        mock_loader.download.return_value = Path("/downloaded.gz")
        mock_loader.load.return_value = []
        inst = UpstoxInstruments()
        source = Path("/custom/source.json.gz")
        inst.load(source=str(source))
        mock_loader.download.assert_called_once_with(source)
        mock_loader.load.assert_called_once_with(Path("/downloaded.gz"))

    @patch("brokers.adapters.upstox.instruments.UpstoxInstrumentLoader")
    def test_load_delegates_download_when_path_missing(self, MockLoader):
        mock_loader = MockLoader.return_value
        mock_loader.download.return_value = Path("/downloaded.gz")
        mock_loader.load.return_value = []
        inst = UpstoxInstruments(cache_path=Path("/nonexistent/path.gz"))
        inst.load()
        mock_loader.download.assert_called_once_with(Path("/nonexistent/path.gz"))

    @patch("brokers.adapters.upstox.instruments.UpstoxInstrumentLoader")
    def test_load_populates_by_symbol_segment(self, MockLoader):
        mock_loader = MockLoader.return_value
        mock_loader.download.return_value = Path("/f")
        mock_loader.load.return_value = [
            _make_def(
                instrument_key="NSE_EQ|RELIANCE",
                symbol="RELIANCE",
                exchange_segment="NSE_EQ",
            ),
        ]
        inst = UpstoxInstruments()
        inst.load()
        assert ("RELIANCE", "NSE_EQ") in inst._by_symbol_segment

    @patch("brokers.adapters.upstox.instruments.UpstoxInstrumentLoader")
    def test_load_populates_expiries(self, MockLoader):
        mock_loader = MockLoader.return_value
        mock_loader.download.return_value = Path("/f")
        mock_loader.load.return_value = [
            _make_def(
                instrument_key="NFO_OPT|NIFTY25JAN24CE",
                symbol="NIFTY25JAN24CE",
                exchange_segment="NFO_OPT",
                expiry="2025-01-30",
                underlying_symbol="NIFTY",
            ),
        ]
        inst = UpstoxInstruments()
        inst.load()
        assert "2025-01-30" in inst._expiries_by_underlying["NIFTY"]

    def test_search_with_loaded_instruments(self):
        inst = UpstoxInstruments()
        d = _make_def()
        inst._by_key["NSE_EQ|RELIANCE"] = d
        results = inst.search("RELIANCE")
        assert len(results) == 1
        assert results[0].symbol == "RELIANCE"

    def test_search_no_match(self):
        inst = UpstoxInstruments()
        inst._by_key["NSE_EQ|RELIANCE"] = _make_def()
        results = inst.search("TCS")
        assert results == []

    def test_search_limit(self):
        inst = UpstoxInstruments()
        for i in range(5):
            inst._by_key[f"K{i}"] = _make_def(
                instrument_key=f"K{i}", symbol=f"REL{i}", name=f"Rel {i}"
            )
        results = inst.search("REL", limit=2)
        assert len(results) == 2

    def test_search_matches_name(self):
        inst = UpstoxInstruments()
        d = _make_def(symbol="XYZ", name="Reliance Industries Ltd")
        inst._by_key["NSE_EQ|XYZ"] = d
        results = inst.search("RELIANCE")
        assert len(results) == 1
        assert results[0].symbol == "XYZ"

    def test_resolve_with_loaded_instruments(self):
        inst = UpstoxInstruments()
        d = _make_def()
        inst._by_symbol_segment[("RELIANCE", "NSE_EQ")] = d
        result = inst.resolve("RELIANCE", "NSE")
        assert result is not None
        assert result.symbol == "RELIANCE"
        assert result.exchange == "NSE"

    def test_resolve_no_match(self):
        inst = UpstoxInstruments()
        result = inst.resolve("NONEXISTENT")
        assert result is None

    def test_instrument_key_with_loaded(self):
        inst = UpstoxInstruments()
        d = _make_def(instrument_key="NSE_EQ|RELIANCE")
        inst._by_symbol_segment[("RELIANCE", "NSE_EQ")] = d
        key = inst.instrument_key("RELIANCE", "NSE")
        assert key == "NSE_EQ|RELIANCE"

    def test_instrument_key_fallback(self):
        inst = UpstoxInstruments()
        key = inst.instrument_key("RELIANCE", "NSE")
        assert key == "NSE_EQ|RELIANCE"

    def test_list_option_expiries_with_data(self):
        inst = UpstoxInstruments()
        inst._expiries_by_underlying["NIFTY"] = {"2025-01-30", "2025-02-27"}
        expiries = inst.list_option_expiries("NIFTY")
        assert expiries == ["2025-01-30", "2025-02-27"]

    def test_list_option_expiries_no_data(self):
        inst = UpstoxInstruments()
        expiries = inst.list_option_expiries("NONEXISTENT")
        assert expiries == []

    def test_to_info(self):
        d = _make_def()
        info = UpstoxInstruments._to_info(d)
        assert isinstance(info, InstrumentInfo)
        assert info.symbol == "RELIANCE"
        assert info.exchange == "NSE"
        assert info.segment == "NSE_EQ"
        assert info.name == "Reliance Industries"
        assert info.lot_size == 1

    def test_load_clears_previous_data(self):
        inst = UpstoxInstruments()
        inst._by_key["OLD"] = _make_def(instrument_key="OLD")
        inst._loaded = True
        with patch.object(inst._loader, "download", return_value=Path("/f")), patch.object(
            inst._loader, "load", return_value=[]
        ):
            inst.load()
        assert "OLD" not in inst._by_key
        assert inst.is_loaded is True

    @patch("brokers.adapters.upstox.instruments.UpstoxInstrumentLoader")
    def test_load_expiry_numeric_timestamp(self, MockLoader):
        mock_loader = MockLoader.return_value
        mock_loader.download.return_value = Path("/f")
        mock_loader.load.return_value = [
            _make_def(
                instrument_key="NFO_OPT|NIFTY25JAN24CE",
                symbol="NIFTY25JAN24CE",
                exchange_segment="NFO_OPT",
                expiry=1738176000000,
                underlying_symbol="NIFTY",
            ),
        ]
        inst = UpstoxInstruments()
        inst.load()
        assert len(inst._expiries_by_underlying["NIFTY"]) == 1

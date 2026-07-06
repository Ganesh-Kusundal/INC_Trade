from unittest.mock import Mock, patch

from inc_trade.ports.instruments import InstrumentInfo

from brokers.adapters.upstox.instrument_definition import UpstoxInstrumentDefinition
from brokers.adapters.upstox.instruments import UpstoxInstruments


@patch("brokers.adapters.upstox.instrument_loader.requests")
def test_upstox_instruments_load_and_resolve(mock_requests):
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.iter_content = lambda chunk_size: [b"line"]
    mock_requests.get.return_value.__enter__ = Mock(return_value=mock_resp)
    mock_requests.get.return_value.__exit__ = Mock(return_value=False)

    defs = [
        UpstoxInstrumentDefinition(
            instrument_key="NSE_EQ|RELIANCE",
            symbol="RELIANCE",
            trading_symbol="RELIANCE",
            exchange="NSE",
            exchange_segment="NSE_EQ",
            name="RELIANCE INDUSTRIES LTD",
            lot_size=1,
        )
    ]

    instruments = UpstoxInstruments()
    with patch.object(instruments._loader, "download", return_value=instruments._cache_path):
        with patch.object(instruments._loader, "load", return_value=defs):
            instruments.load()

    info = instruments.resolve("RELIANCE", "NSE")
    assert isinstance(info, InstrumentInfo)
    assert info.symbol == "RELIANCE"
    assert info.exchange == "NSE"
    assert info.lot_size == 1


def test_upstox_instruments_search():
    instruments = UpstoxInstruments()
    d = UpstoxInstrumentDefinition(
        instrument_key="NSE_EQ|RELIANCE",
        symbol="RELIANCE",
        trading_symbol="RELIANCE",
        exchange="NSE",
        exchange_segment="NSE_EQ",
        name="RELIANCE INDUSTRIES",
        lot_size=1,
    )
    instruments._by_key[d.instrument_key] = d
    instruments._by_symbol_segment[("RELIANCE", "NSE_EQ")] = d

    results = instruments.search("REL")
    assert len(results) == 1
    assert results[0].symbol == "RELIANCE"

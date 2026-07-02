import pytest
from unittest.mock import Mock, patch

from brokers.adapters.upstox.instruments import UpstoxInstruments
from brokers.ports.instruments import InstrumentInfo

@patch('brokers.adapters.upstox.instruments.requests')
def test_upstox_instruments_load_and_resolve(mock_requests):
    mock_resp = Mock()
    mock_resp.text = "instrument_key,exchange_token,tradingsymbol,name,last_price,expiry,strike,tick_size,lot_size,instrument_type,option_type,exchange\n" \
                     "NSE_EQ|11536,11536,RELIANCE,RELIANCE INDUSTRIES LTD,2500,2023-11-20,,0.05,1,EQUITY,,NSE\n"
    
    mock_requests.get.return_value = mock_resp
    
    instruments = UpstoxInstruments()
    instruments.load("NSE")
    
    mock_requests.get.assert_called_once()
    
    info = instruments.resolve("RELIANCE", "NSE")
    assert isinstance(info, InstrumentInfo)
    assert info.symbol == "RELIANCE"
    assert info.exchange == "NSE"
    assert info.lot_size == 1

def test_upstox_instruments_search():
    instruments = UpstoxInstruments()
    instruments._instruments = [
        InstrumentInfo(symbol="RELIANCE", exchange="NSE", lot_size=1),
        InstrumentInfo(symbol="HDFC", exchange="NSE", lot_size=1),
    ]
    
    results = instruments.search("REL")
    assert len(results) == 1
    assert results[0].symbol == "RELIANCE"

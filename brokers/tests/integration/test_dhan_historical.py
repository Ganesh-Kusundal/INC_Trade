import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock

from brokers.adapters.dhan.historical import DhanHistorical
from brokers.domain.entities import Candle

def test_dhan_get_historical_candles():
    client = Mock()
    # Dhan typically returns a columnar format for charting
    client.post.return_value = {
        "status": "success",
        "data": {
            "start_Time": [1700438400],
            "open": [2500.0],
            "high": [2510.0],
            "low": [2490.0],
            "close": [2505.0],
            "volume": [10000]
        }
    }
    
    resolver = Mock()
    ref = Mock()
    ref.exchange_segment = "NSE_EQ"
    ref.security_id_str.return_value = "11536"
    ref.instrument_type = "EQUITY"
    resolver.resolve.return_value = ref

    historical = DhanHistorical(client, resolver)
    start = datetime(2023, 11, 20)
    end = datetime(2023, 11, 21)

    candles = historical.get_historical_candles(
        symbol="RELIANCE",
        exchange="NSE",
        start_time=start,
        end_time=end,
        resolution="1D"
    )

    assert len(candles) == 1
    c = candles[0]
    assert isinstance(c, Candle)
    assert c.symbol == "RELIANCE"
    assert c.open == Decimal("2500")
    assert c.high == Decimal("2510")
    assert c.low == Decimal("2490")
    assert c.close == Decimal("2505")
    assert c.volume == 10000
    
    client.post.assert_called_once()
    args, kwargs = client.post.call_args
    payload = kwargs["json"]
    assert payload["fromDate"] == "2023-11-20"
    assert payload["toDate"] == "2023-11-21"

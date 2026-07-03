from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock

from brokers.adapters.upstox.historical import UpstoxHistorical
from brokers.config.endpoints import Upstox
from brokers.domain.entities import Candle


def test_get_historical_candles():
    client = Mock()
    client.get.return_value = {
        "status": "success",
        "data": {
            "candles": [
                ["2023-11-20T00:00:00+05:30", 2500.0, 2510.0, 2490.0, 2505.0, 10000]
            ]
        },
    }

    historical = UpstoxHistorical(client, urls=Upstox.production())
    start = datetime(2023, 11, 20)
    end = datetime(2023, 11, 21)

    candles = historical.get_historical_candles(
        symbol="RELIANCE",
        exchange="NSE",
        start_time=start,
        end_time=end,
        resolution="1D",
    )

    assert len(candles) == 1
    c = candles[0]
    assert isinstance(c, Candle)
    assert c.symbol == "RELIANCE"
    assert c.open == Decimal("2500.0")
    assert c.high == Decimal("2510.0")
    assert c.low == Decimal("2490.0")
    assert c.close == Decimal("2505.0")
    assert c.volume == 10000

    client.get.assert_called_once_with(
        "/v2/historical-candle/NSE_EQ|RELIANCE/day/2023-11-21/2023-11-20"
    )

"""Unit tests for HistoricalAdapter."""

import pandas as pd

from brokers.dhan.historical import HistoricalAdapter


def test_daily_uses_historical_endpoint(fake_client, resolver):
    fake_client.set_response(
        "POST",
        "/charts/historical",
        {
            "data": [
                {
                    "date": "2026-01-02",
                    "open": 2440,
                    "high": 2460,
                    "low": 2435,
                    "close": 2455,
                    "volume": 1000000,
                },
            ]
        },
    )
    adapter = HistoricalAdapter(fake_client, resolver)
    adapter.get_historical("RELIANCE", "NSE", "2026-01-01", "2026-01-31", timeframe="1D")

    # Verify the daily endpoint was used
    assert len(fake_client.calls_for("POST", "/charts/historical")) == 1
    # Intraday endpoint should NOT have been called
    assert len(fake_client.calls_for("POST", "/charts/intraday")) == 0


def test_intraday_uses_intraday_endpoint(fake_client, resolver):
    fake_client.set_response(
        "POST",
        "/charts/intraday",
        {
            "data": [
                {
                    "timestamp": 1735780500,
                    "open": 2440,
                    "high": 2445,
                    "low": 2438,
                    "close": 2443,
                    "volume": 5000,
                },
            ]
        },
    )
    adapter = HistoricalAdapter(fake_client, resolver)
    adapter.get_historical("RELIANCE", "NSE", "2026-01-02", "2026-01-02", timeframe="5")

    # Verify the intraday endpoint was used
    assert len(fake_client.calls_for("POST", "/charts/intraday")) == 1
    # Daily endpoint should NOT have been called
    assert len(fake_client.calls_for("POST", "/charts/historical")) == 0

    # Verify the interval was included in the payload
    payloads = fake_client.calls_for("POST", "/charts/intraday")
    assert payloads[0]["interval"] == "5"


def test_mcx_session_times(fake_client, resolver):
    fake_client.set_response(
        "POST",
        "/charts/intraday",
        {
            "data": [
                {
                    "timestamp": 1735780500,
                    "open": 72000,
                    "high": 72100,
                    "low": 71900,
                    "close": 72050,
                    "volume": 100,
                },
            ]
        },
    )
    adapter = HistoricalAdapter(fake_client, resolver)
    adapter.get_historical("GOLD", "MCX", "2026-01-02", "2026-01-02", timeframe="5")

    payloads = fake_client.calls_for("POST", "/charts/intraday")
    assert len(payloads) == 1
    payload = payloads[0]
    # MCX session opens at 09:00 and closes at 23:30
    assert payload["fromDate"].endswith("09:00:00")
    assert payload["toDate"].endswith("23:30:00")


def test_instrument_type_detection(resolver):
    """Verify _get_instrument_type maps correctly: INDEX→EQUITY, NFO→OPTIDX, MCX→FUTCOM."""
    # NIFTY is an INDEX instrument → should map to "EQUITY"
    nifty = resolver.resolve("NIFTY", "INDEX")
    assert HistoricalAdapter._get_instrument_type(nifty) == "EQUITY"

    # RELIANCE is an EQUITY instrument → should map to "EQUITY"
    reliance = resolver.resolve("RELIANCE", "NSE")
    assert HistoricalAdapter._get_instrument_type(reliance) == "EQUITY"

    # NIFTY options on NFO → should map to "OPTIDX"
    nifty_opt = resolver.resolve("NIFTY 26 JUN 25000 CE", "NFO")
    assert HistoricalAdapter._get_instrument_type(nifty_opt) == "OPTIDX"

    # GOLD futures on MCX → should map to "FUTCOM"
    gold = resolver.resolve("GOLD AUG FUT", "MCX")
    assert HistoricalAdapter._get_instrument_type(gold) == "FUTCOM"


def test_parse_dataframe(fake_client, resolver):
    fake_client.set_response(
        "POST",
        "/charts/historical",
        {
            "data": [
                {
                    "date": "2026-01-02",
                    "open": 2440,
                    "high": 2460,
                    "low": 2435,
                    "close": 2455,
                    "volume": 1000000,
                },
                {
                    "date": "2026-01-03",
                    "open": 2455,
                    "high": 2475,
                    "low": 2450,
                    "close": 2470,
                    "volume": 1200000,
                },
            ]
        },
    )
    adapter = HistoricalAdapter(fake_client, resolver)
    df = adapter.get_historical("RELIANCE", "NSE", "2026-01-01", "2026-01-31", timeframe="1D")

    assert isinstance(df, pd.DataFrame)
    required_cols = {
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "oi",
        "symbol",
        "exchange",
        "timeframe",
    }
    assert required_cols.issubset(set(df.columns))
    assert len(df) == 2
    assert list(df.columns) == [
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "oi",
        "symbol",
        "exchange",
        "timeframe",
    ]

"""Unit tests for UpstoxHistorical."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from brokers.adapters.upstox.historical import UpstoxHistorical
from brokers.adapters.upstox.urls import resolve_upstox_urls


class TestUpstoxHistoricalGetHistoricalCandles:
    def test_get_historical_candles_endpoint_format(self):
        client = MagicMock()
        client.get.return_value = {"data": {"candles": []}}
        urls = resolve_upstox_urls("LIVE")
        h = UpstoxHistorical(client, urls=urls)
        h.get_historical_candles(
            "RELIANCE", "NSE_EQ",
            datetime(2025, 1, 1), datetime(2025, 1, 31), "1D",
        )
        call_args = client.get.call_args
        endpoint = call_args[0][0]
        assert "/v2/historical-candle/" in endpoint
        assert "NSE_EQ" in endpoint or "RELIANCE" in endpoint

    def test_get_historical_candles_resolves_1m(self):
        client = MagicMock()
        client.get.return_value = {"data": {"candles": []}}
        urls = resolve_upstox_urls("LIVE")
        h = UpstoxHistorical(client, urls=urls)
        h.get_historical_candles(
            "RELIANCE", "NSE_EQ",
            datetime(2025, 1, 1), datetime(2025, 1, 31), "1m",
        )
        endpoint = client.get.call_args[0][0]
        assert "minute" in endpoint

    def test_get_historical_candles_resolves_5m(self):
        client = MagicMock()
        client.get.return_value = {"data": {"candles": []}}
        urls = resolve_upstox_urls("LIVE")
        h = UpstoxHistorical(client, urls=urls)
        h.get_historical_candles(
            "RELIANCE", "NSE_EQ",
            datetime(2025, 1, 1), datetime(2025, 1, 31), "5m",
        )
        endpoint = client.get.call_args[0][0]
        assert "5minute" in endpoint

    def test_get_historical_candles_resolves_15m(self):
        client = MagicMock()
        client.get.return_value = {"data": {"candles": []}}
        urls = resolve_upstox_urls("LIVE")
        h = UpstoxHistorical(client, urls=urls)
        h.get_historical_candles(
            "RELIANCE", "NSE_EQ",
            datetime(2025, 1, 1), datetime(2025, 1, 31), "15m",
        )
        endpoint = client.get.call_args[0][0]
        assert "15minute" in endpoint

    def test_get_historical_candles_resolves_1D(self):
        client = MagicMock()
        client.get.return_value = {"data": {"candles": []}}
        urls = resolve_upstox_urls("LIVE")
        h = UpstoxHistorical(client, urls=urls)
        h.get_historical_candles(
            "RELIANCE", "NSE_EQ",
            datetime(2025, 1, 1), datetime(2025, 1, 31), "1D",
        )
        endpoint = client.get.call_args[0][0]
        assert "day" in endpoint

    def test_get_historical_candles_exception_returns_empty(self):
        client = MagicMock()
        client.get.side_effect = Exception("network error")
        urls = resolve_upstox_urls("LIVE")
        h = UpstoxHistorical(client, urls=urls)
        result = h.get_historical_candles(
            "RELIANCE", "NSE_EQ",
            datetime(2025, 1, 1), datetime(2025, 1, 31), "1D",
        )
        assert result == []


class TestUpstoxHistoricalParse:
    def test_parse_valid_candle_list_of_lists(self):
        data = {
            "data": {
                "candles": [
                    ["2025-01-15T09:15:00+05:30", 2500, 2550, 2490, 2520, 1000],
                    ["2025-01-16T09:15:00+05:30", 2520, 2560, 2510, 2540, 1200],
                ]
            }
        }
        candles = UpstoxHistorical._parse(data, "RELIANCE")
        assert len(candles) == 2
        assert candles[0].symbol == "RELIANCE"
        assert candles[0].open == Decimal("2500")
        assert candles[0].high == Decimal("2550")
        assert candles[0].low == Decimal("2490")
        assert candles[0].close == Decimal("2520")
        assert candles[0].volume == 1000
        assert candles[1].close == Decimal("2540")

    def test_parse_columnar_format(self):
        data = {
            "data": {
                "candles": [
                    {"timestamp": "2025-01-15", "open": 100},
                ]
            }
        }
        candles = UpstoxHistorical._parse(data, "RELIANCE")
        assert candles == []

    def test_parse_empty_data(self):
        candles = UpstoxHistorical._parse({}, "RELIANCE")
        assert candles == []

    def test_parse_empty_candles_list(self):
        data = {"data": {"candles": []}}
        candles = UpstoxHistorical._parse(data, "RELIANCE")
        assert candles == []

    def test_parse_malformed_timestamp_skipped(self):
        data = {
            "data": {
                "candles": [
                    ["not-a-date", 100, 110, 90, 105, 500],
                    ["2025-01-15T09:15:00+05:30", 200, 210, 190, 205, 600],
                ]
            }
        }
        candles = UpstoxHistorical._parse(data, "RELIANCE")
        assert len(candles) == 1
        assert candles[0].open == Decimal("200")

    def test_parse_candle_without_volume(self):
        data = {
            "data": {
                "candles": [
                    ["2025-01-15T09:15:00+05:30", 100, 110, 90, 105],
                ]
            }
        }
        candles = UpstoxHistorical._parse(data, "RELIANCE")
        assert len(candles) == 1
        assert candles[0].volume == 0


class TestUpstoxHistoricalGetIntraday:
    def test_get_intraday_candles_v3(self):
        client = MagicMock()
        client.get.return_value = {"data": {"candles": []}}
        urls = resolve_upstox_urls("LIVE")
        h = UpstoxHistorical(client, urls=urls)
        h.get_intraday_candles_v3("RELIANCE", "NSE_EQ", "minute", 15, "2025-01-15")
        client.get.assert_called_once()

    def test_get_intraday_candles_v3_exception_returns_empty(self):
        client = MagicMock()
        client.get.side_effect = Exception("timeout")
        urls = resolve_upstox_urls("LIVE")
        h = UpstoxHistorical(client, urls=urls)
        result = h.get_intraday_candles_v3("RELIANCE", "NSE_EQ", "minute", 15, "2025-01-15")
        assert result == []


class TestUpstoxHistoricalGetCandlesAlias:
    def test_get_candles_delegates_to_get_historical_candles(self):
        client = MagicMock()
        client.get.return_value = {"data": {"candles": []}}
        urls = resolve_upstox_urls("LIVE")
        h = UpstoxHistorical(client, urls=urls)
        start = datetime(2025, 1, 1)
        end = datetime(2025, 1, 31)
        result = h.get_candles("RELIANCE", "NSE_EQ", start, end, "1D")
        client.get.assert_called_once()
        assert isinstance(result, list)

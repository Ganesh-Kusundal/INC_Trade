"""Unit tests for Upstox market data adapter."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from inc_trade.domain import MarketDepth, Quote

from brokers.adapters.upstox.market_data import UpstoxMarketData


class TestUpstoxMarketData:
    def setup_method(self):
        self.client = MagicMock()
        self.urls = MagicMock()
        self.instruments = MagicMock()
        self.instruments.is_loaded = True
        self.instruments.instrument_key.return_value = "NSE_EQ|RELIANCE"
        self.market_data = UpstoxMarketData(self.client, self.urls, self.instruments)

    def test_ltp_returns_decimal(self):
        self.client.get.return_value = {
            "data": {"NSE_EQ|RELIANCE": {"last_price": 2800.50}}
        }
        result = self.market_data.ltp("RELIANCE")
        assert result == Decimal("2800.50")
        self.client.get.assert_called_once_with(
            self.urls.market_quote_ltp_url(),
            params={"instrument_key": "NSE_EQ|RELIANCE"},
        )

    def test_ltp_empty_feed_returns_zero(self):
        self.client.get.return_value = {"data": {}}
        result = self.market_data.ltp("RELIANCE")
        assert result == Decimal("0")

    def test_ltp_missing_last_price_returns_zero(self):
        self.client.get.return_value = {
            "data": {"NSE_EQ|RELIANCE": {"open": 2700}}
        }
        result = self.market_data.ltp("RELIANCE")
        assert result == Decimal("0")

    def test_quote_returns_quote_object(self):
        self.client.get.return_value = {
            "data": {
                "NSE_EQ|RELIANCE": {
                    "last_price": 2800.0,
                    "volume": 100000,
                    "ohlc": {
                        "open": 2750.0,
                        "high": 2850.0,
                        "low": 2700.0,
                        "close": 2780.0,
                    },
                }
            }
        }
        result = self.market_data.quote("RELIANCE")
        assert isinstance(result, Quote)
        assert result.symbol == "RELIANCE"
        assert result.ltp == Decimal("2800.0")
        assert result.open == Decimal("2750.0")
        assert result.volume == 100000

    def test_depth_returns_market_depth(self):
        self.client.get.return_value = {
            "data": {
                "NSE_EQ|RELIANCE": {
                    "depth": {
                        "buy": [{"price": 2799, "quantity": 100, "orders": 5}],
                        "sell": [{"price": 2801, "quantity": 200, "orders": 3}],
                    }
                }
            }
        }
        result = self.market_data.depth("RELIANCE")
        assert isinstance(result, MarketDepth)
        assert result.symbol == "RELIANCE"
        assert len(result.bids) == 1
        assert len(result.asks) == 1
        assert result.bids[0].price == Decimal("2799")
        assert result.asks[0].quantity == 200

    def test_ltp_batch_returns_multiple_symbols(self):
        self.instruments.instrument_key.side_effect = lambda sym, ex: f"NSE_EQ|{sym}"
        self.client.get.return_value = {
            "data": {
                "NSE_EQ|RELIANCE": {"last_price": 2800},
                "NSE_EQ|TCS": {"last_price": 3500},
            }
        }
        result = self.market_data.ltp_batch(["RELIANCE", "TCS"])
        assert result["RELIANCE"] == Decimal("2800")
        assert result["TCS"] == Decimal("3500")

    def test_quote_batch_returns_multiple_symbols(self):
        self.instruments.instrument_key.side_effect = lambda sym, ex: f"NSE_EQ|{sym}"
        self.client.get.return_value = {
            "data": {
                "NSE_EQ|RELIANCE": {
                    "last_price": 2800,
                    "volume": 50000,
                    "ohlc": {},
                },
                "NSE_EQ|TCS": {
                    "last_price": 3500,
                    "volume": 30000,
                    "ohlc": {},
                },
            }
        }
        result = self.market_data.quote_batch(["RELIANCE", "TCS"])
        assert isinstance(result["RELIANCE"], Quote)
        assert isinstance(result["TCS"], Quote)
        assert result["RELIANCE"].ltp == Decimal("2800")
        assert result["TCS"].ltp == Decimal("3500")

    def test_find_symbol_data_direct_key(self):
        feed = {"NSE_EQ|RELIANCE": {"last_price": 100}}
        result = self.market_data._find_symbol_data(feed, "NSE_EQ|RELIANCE", "RELIANCE")
        assert result == {"last_price": 100}

    def test_find_symbol_data_colon_fallback(self):
        feed = {"NSE_EQ:RELIANCE": {"last_price": 100}}
        result = self.market_data._find_symbol_data(feed, "NSE_EQ|RELIANCE", "RELIANCE")
        assert result == {"last_price": 100}

    def test_find_symbol_data_instrument_token_match(self):
        feed = {"OTHER_KEY": {"instrument_token": "NSE_EQ|RELIANCE", "last_price": 100}}
        result = self.market_data._find_symbol_data(feed, "NSE_EQ|RELIANCE", "RELIANCE")
        assert result["last_price"] == 100

    def test_find_symbol_data_symbol_in_key(self):
        feed = {"NSE_EQ:RELIANCE": {"last_price": 100}}
        result = self.market_data._find_symbol_data(feed, "NSE_EQ|RELIANCE", "RELIANCE")
        assert result == {"last_price": 100}

    def test_find_symbol_data_single_entry_fallback(self):
        feed = {"RANDOM_KEY": {"last_price": 100}}
        result = self.market_data._find_symbol_data(feed, "NSE_EQ|RELIANCE", "RELIANCE")
        assert result == {"last_price": 100}

    def test_find_symbol_data_empty_feed(self):
        result = self.market_data._find_symbol_data({}, "NSE_EQ|RELIANCE", "RELIANCE")
        assert result == {}

    def test_find_symbol_data_no_match_multiple(self):
        feed = {
            "KEY_A": {"instrument_token": "OTHER"},
            "KEY_B": {"instrument_token": "ANOTHER"},
        }
        result = self.market_data._find_symbol_data(feed, "NSE_EQ|RELIANCE", "RELIANCE")
        assert result == {}

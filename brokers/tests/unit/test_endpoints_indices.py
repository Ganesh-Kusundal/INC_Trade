"""Tests for endpoints and indices configuration."""

import pytest
from inc_trade.config.endpoints import Dhan, Upstox, _UpstoxUrls
from inc_trade.config.indices import (
    INDEX_SYMBOLS,
    INDEX_TO_FNO_EXCHANGE,
    get_index_entry,
    index_upstox_key,
    is_index,
    list_indices,
    upstox_index_segment,
)

from brokers.adapters.dhan.index_registry import DhanIndexRegistry


class TestDhanEndpoints:
    def test_rest_base(self):
        assert Dhan.REST_BASE == "https://api.dhan.co/v2"

    def test_sandbox_base(self):
        assert Dhan.SANDBOX_REST_BASE == "https://sandbox.dhan.co/v2"

    def test_production_classmethod(self):
        assert Dhan.production() == Dhan.REST_BASE

    def test_sandbox_classmethod(self):
        assert Dhan.sandbox() == Dhan.SANDBOX_REST_BASE

    def test_websocket_endpoints(self):
        assert Dhan.WS_DEPTH_20.startswith("wss://")
        assert Dhan.WS_DEPTH_200.startswith("wss://")

    def test_auth_url(self):
        assert "dhan.co" in Dhan.GENERATE_TOKEN_URL

    def test_instrument_csv(self):
        assert Dhan.INSTRUMENT_CSV.endswith(".csv")

    def test_rest_paths(self):
        assert Dhan.MARKETFEED_LTP == "/marketfeed/ltp"
        assert Dhan.ORDERS == "/orders"
        assert Dhan.OPTION_CHAIN == "/optionchain"
        assert Dhan.KILL_SWITCH == "/killswitch"

    def test_mcx_instrument_url(self):
        assert "MCX_COMM" in Dhan.INSTRUMENT_MCX_DETAILED


class TestUpstoxEndpoints:
    def test_production_factory(self):
        prod = Upstox.production()
        assert isinstance(prod, _UpstoxUrls)
        assert prod.is_sandbox is False
        assert prod.base_v2 == "https://api.upstox.com"
        assert prod.base_hft == "https://api-hft.upstox.com"

    def test_sandbox_factory(self):
        sandbox = Upstox.sandbox()
        assert isinstance(sandbox, _UpstoxUrls)
        assert sandbox.is_sandbox is True
        assert "sandbox" in sandbox.base_v2

    def test_auth_dialog_url_standalone(self):
        url = Upstox.auth_dialog_url(is_sandbox=False)
        assert "api.upstox.com" in url
        assert "v2/login/authorization/dialog" in url

    def test_auth_dialog_url_sandbox(self):
        url = Upstox.auth_dialog_url(is_sandbox=True)
        assert "sandbox" in url

    def test_order_urls(self):
        prod = Upstox.production()
        assert "/v3/order/place" in prod.place_order_v3_url()
        assert "/v3/order/modify" in prod.modify_order_v3_url()
        assert "/v3/order/cancel" in prod.cancel_order_v3_url()

    def test_market_data_urls(self):
        prod = Upstox.production()
        assert "/v2/market-quote/ltp" in prod.market_quote_ltp_url()
        assert "/v2/market-quote/ohlc" in prod.market_quote_ohlc_url()

    def test_portfolio_urls(self):
        prod = Upstox.production()
        assert "/v2/portfolio/short-term-positions" in prod.positions_url()
        assert "/v2/portfolio/long-term-holdings" in prod.holdings_url()

    def test_historical_candle_url(self):
        prod = Upstox.production()
        url = prod.historical_candle_url("NSE_EQ|INE669E01016", "1d", "2024-01-01")
        assert "historical-candle" in url
        assert "2024-01-01" in url

    def test_historical_candle_url_with_from_date(self):
        prod = Upstox.production()
        url = prod.historical_candle_url("key", "1d", "2024-01-31", "2024-01-01")
        assert "2024-01-01" in url

    def test_v3_historical_url_encodes_key(self):
        prod = Upstox.production()
        url = prod.historical_candle_v3_url("NSE_INDEX|Nifty 50", "minute", 1, "2024-01-01")
        assert "NSE_INDEX" in url
        assert "Nifty%2050" in url or "Nifty+50" in url

    def test_frozen_dataclass(self):
        prod = Upstox.production()
        with pytest.raises(AttributeError):
            prod.base_v2 = "changed"

    def test_option_chain_url(self):
        prod = Upstox.production()
        assert "/v2/option/chain" in prod.option_chain_url()

    def test_gtt_urls(self):
        prod = Upstox.production()
        assert "/gtt/place" in prod.gtt_place_url()
        assert "/gtt/modify" in prod.gtt_modify_url()
        assert "/gtt/cancel" in prod.gtt_cancel_url()

    def test_feed_authorize(self):
        prod = Upstox.production()
        assert "feed" in prod.feed_authorize_v2_url()
        assert "feed" in prod.feed_authorize_v3_url()

    def test_instrument_complete(self):
        prod = Upstox.production()
        assert "assets.upstox.com" in prod.instrument_complete_url()


class TestIndices:
    def test_nifty_is_index(self):
        assert is_index("NIFTY") is True

    def test_banknifty_is_index(self):
        assert is_index("BANKNIFTY") is True

    def test_case_insensitive(self):
        assert is_index("nifty") is True
        assert is_index("BankNifty") is True

    def test_equity_not_index(self):
        assert is_index("RELIANCE") is False
        assert is_index("TCS") is False

    def test_empty_string(self):
        assert is_index("") is False

    def test_whitespace_stripped(self):
        assert is_index("  NIFTY  ") is True

    def test_get_index_entry(self):
        entry = get_index_entry("NIFTY")
        assert entry is not None
        assert entry.canonical_name == "NIFTY 50"
        assert entry.upstox_segment == "NSE_INDEX"

    def test_get_index_entry_case_insensitive(self):
        entry = get_index_entry("banknifty")
        assert entry is not None
        assert entry.canonical_name == "NIFTY BANK"

    def test_get_index_entry_unknown(self):
        assert get_index_entry("RELIANCE") is None

    def test_dhan_index_registry(self):
        assert DhanIndexRegistry.lookup("NIFTY") is not None
        assert DhanIndexRegistry.security_id("NIFTY") == "13"
        assert DhanIndexRegistry.exchange("NIFTY") == "INDEX"
        assert DhanIndexRegistry.lookup("RELIANCE") is None

    def test_upstox_index_segment(self):
        assert upstox_index_segment("NIFTY") == "NSE_INDEX"
        assert upstox_index_segment("SENSEX") == "BSE_INDEX"
        assert upstox_index_segment("DOW") == "GLOBAL_INDEX"
        assert upstox_index_segment("RELIANCE") is None

    def test_index_upstox_key(self):
        key = index_upstox_key("NIFTY")
        assert key == "NSE_INDEX|Nifty 50"

    def test_index_upstox_key_banknifty(self):
        key = index_upstox_key("BANKNIFTY")
        assert key == "NSE_INDEX|Nifty Bank"

    def test_index_upstox_key_sensex(self):
        key = index_upstox_key("SENSEX")
        assert key == "BSE_INDEX|SENSEX"

    def test_index_upstox_key_unknown(self):
        assert index_upstox_key("RELIANCE") is None

    def test_index_symbols_frozenset(self):
        assert isinstance(INDEX_SYMBOLS, frozenset)
        assert "NIFTY" in INDEX_SYMBOLS
        assert "BANKNIFTY" in INDEX_SYMBOLS
        assert "SENSEX" in INDEX_SYMBOLS
        assert len(INDEX_SYMBOLS) > 30

    def test_fno_exchange_mapping(self):
        assert INDEX_TO_FNO_EXCHANGE["NIFTY"] == "NFO"
        assert INDEX_TO_FNO_EXCHANGE["BANKNIFTY"] == "NFO"
        assert INDEX_TO_FNO_EXCHANGE["FINNIFTY"] == "NFO"
        assert INDEX_TO_FNO_EXCHANGE["SENSEX"] == "BFO"

    def test_list_indices(self):
        result = list_indices()
        assert isinstance(result, list)
        assert len(result) > 30
        first = result[0]
        assert "symbol" in first
        assert "name" in first
        assert "upstox_segment" in first
        assert "upstox_segment" in first

    def test_aliases_share_same_canonical(self):
        nifty = get_index_entry("NIFTY")
        nifty50 = get_index_entry("NIFTY50")
        assert nifty.canonical_name == nifty50.canonical_name

    def test_bse_indices(self):
        assert is_index("BSE100") is True
        assert is_index("BSE500") is True
        assert is_index("BSEMIDCAP") is True

    def test_global_indices(self):
        assert is_index("DOW") is True
        assert is_index("NASDAQ") is True
        assert is_index("S&P500") is True

    def test_dhan_security_ids(self):
        assert DhanIndexRegistry.security_id("NIFTY") == "13"
        assert DhanIndexRegistry.security_id("BANKNIFTY") == "25"
        assert DhanIndexRegistry.security_id("FINNIFTY") == "27"
        assert DhanIndexRegistry.security_id("RELIANCE") is None

    def test_index_entry_frozen(self):
        entry = get_index_entry("NIFTY")
        with pytest.raises(AttributeError):
            entry.canonical_name = "changed"

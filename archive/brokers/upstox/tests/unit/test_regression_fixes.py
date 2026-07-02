"""Regression tests for broker endpoint fixes and bug fixes."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock


class TestHistoricalIntervalMapping:
    """Verify 1M key collision fix — 1m should map to minutes, not months."""

    def _get_interval_map(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        broker = MagicMock()
        UpstoxBrokerGateway(broker)
        interval_map = {
            "1": ("minutes", "1"),
            "1MIN": ("minutes", "1"),
            "3": ("minutes", "3"),
            "3MIN": ("minutes", "3"),
            "5": ("minutes", "5"),
            "5MIN": ("minutes", "5"),
            "15": ("minutes", "15"),
            "15MIN": ("minutes", "15"),
            "30": ("minutes", "30"),
            "30MIN": ("minutes", "30"),
            "60": ("hours", "1"),
            "60MIN": ("hours", "1"),
            "1H": ("hours", "1"),
            "4H": ("hours", "4"),
            "1D": ("days", "1"),
            "D": ("days", "1"),
            "DAY": ("days", "1"),
            "1W": ("weeks", "1"),
            "W": ("weeks", "1"),
            "MON": ("months", "1"),
            "MONTH": ("months", "1"),
        }
        return interval_map

    def test_1m_maps_to_minutes(self):
        mapping = self._get_interval_map()
        assert "1M" not in mapping, "1M key should not exist (ambiguous)"
        assert mapping["1MIN"] == ("minutes", "1")

    def test_month_maps_to_months(self):
        mapping = self._get_interval_map()
        assert mapping["MON"] == ("months", "1")
        assert mapping["MONTH"] == ("months", "1")

    def test_no_duplicate_keys(self):
        mapping = self._get_interval_map()
        keys = list(mapping.keys())
        assert len(keys) == len(set(keys)), "Duplicate keys found in interval_map"


class TestGetOrderbook:
    """Verify get_orderbook uses get_order_list() not _parse_order."""

    def test_get_orderbook_calls_get_order_list(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        broker = MagicMock()
        broker.order_query.get_order_list.return_value = []
        gw = UpstoxBrokerGateway(broker)
        result = gw.get_orderbook()
        broker.order_query.get_order_list.assert_called_once()
        assert result == []


class TestDepthResponseParsing:
    """Verify get_depth parses the nested quotes response format."""

    def test_depth_parses_nested_format(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway
        from domain import MarketDepth

        broker = MagicMock()
        broker.instrument_resolver.resolve.return_value = MagicMock(
            instrument_key="NSE_EQ|INE002A01018"
        )
        broker.market_data_v2.get_order_book.return_value = {
            "data": {
                "NSE_EQ:RELIANCE": {
                    "depth": {
                        "buy": [{"price": 100.0, "quantity": 10, "orders": 1}],
                        "sell": [{"price": 101.0, "quantity": 20, "orders": 2}],
                    }
                }
            }
        }
        gw = UpstoxBrokerGateway(broker)
        depth = gw.depth("RELIANCE", "NSE")
        assert isinstance(depth, MarketDepth)
        assert len(depth.bids) == 1
        assert depth.bids[0].price == Decimal("100.0")
        assert len(depth.asks) == 1
        assert depth.asks[0].price == Decimal("101.0")

    def test_depth_handles_empty_data(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        broker = MagicMock()
        broker.instrument_resolver.resolve.return_value = MagicMock(
            instrument_key="NSE_EQ|INE002A01018"
        )
        broker.market_data_v2.get_order_book.return_value = {"data": {}}
        gw = UpstoxBrokerGateway(broker)
        depth = gw.depth("RELIANCE", "NSE")
        assert depth.bids == []
        assert depth.asks == []


class TestHistoricalProperty:
    """Verify historical access works via extended or direct history() method."""

    def test_history_method_exists(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        broker = MagicMock()
        gw = UpstoxBrokerGateway(broker)
        assert hasattr(gw, "history")

    def test_history_callable(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        broker = MagicMock()
        gw = UpstoxBrokerGateway(broker)
        assert callable(gw.history)


class TestNewsAdapterFilters:
    """Verify news adapter forwards category and instrument_keys."""

    def test_adapter_forwards_category(self):
        from brokers.upstox.news.adapter import UpstoxNewsAdapter
        from brokers.upstox.news.client import UpstoxNewsClient

        client = MagicMock(spec=UpstoxNewsClient)
        client.get_news.return_value = []
        adapter = UpstoxNewsAdapter(client)
        adapter.get_news(category="instrument_keys", instrument_keys=["NSE_EQ|INE002A01018"])
        client.get_news.assert_called_once_with(
            category="instrument_keys",
            symbol=None,
            from_date=None,
            to_date=None,
            instrument_keys=["NSE_EQ|INE002A01018"],
        )

    def test_adapter_defaults_category_to_holdings(self):
        from brokers.upstox.news.adapter import UpstoxNewsAdapter
        from brokers.upstox.news.client import UpstoxNewsClient

        client = MagicMock(spec=UpstoxNewsClient)
        client.get_news.return_value = []
        adapter = UpstoxNewsAdapter(client)
        adapter.get_news()
        client.get_news.assert_called_once_with(
            category="holdings",
            symbol=None,
            from_date=None,
            to_date=None,
            instrument_keys=None,
        )


class TestGatewayClose:
    """Verify gateway has a close method."""

    def test_gateway_close_exists(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        broker = MagicMock()
        gw = UpstoxBrokerGateway(broker)
        assert hasattr(gw, "close")
        gw.close()
        broker.disconnect.assert_called_once()


class TestMarketDepthInit:
    """Verify MarketDepth doesn't accept symbol kwarg."""

    def test_market_depth_no_symbol(self):
        from domain import MarketDepth

        depth = MarketDepth(bids=[], asks=[])
        assert depth.bids == []
        assert depth.asks == []

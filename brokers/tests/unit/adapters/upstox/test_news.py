"""Unit tests for Upstox news adapter."""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.adapters.upstox.news import UpstoxNews
from inc_trade.config.endpoints import Upstox


def _make_adapter(client_get_return=None):
    client = MagicMock()
    client.get.return_value = client_get_return
    urls = Upstox.production()
    return UpstoxNews(client, urls), client


class TestGetNews:
    def test_default_category(self):
        adapter, client = _make_adapter({"data": {"items": [{"headline": "hi"}]}})
        adapter.get_news()
        _, kwargs = client.get.call_args
        assert kwargs["params"]["category"] == "holdings"

    def test_category_holdings(self):
        adapter, client = _make_adapter({"data": []})
        adapter.get_news(category="holdings")
        _, kwargs = client.get.call_args
        assert kwargs["params"]["category"] == "holdings"

    def test_instrument_keys(self):
        adapter, client = _make_adapter({"data": []})
        adapter.get_news(category="instrument_keys", instrument_keys=["KEY1", "KEY2"])
        _, kwargs = client.get.call_args
        assert kwargs["params"]["instrument_keys"] == "KEY1,KEY2"

    def test_date_range(self):
        adapter, client = _make_adapter({"data": []})
        adapter.get_news(from_date="2024-01-01", to_date="2024-12-31")
        _, kwargs = client.get.call_args
        assert kwargs["params"]["from"] == "2024-01-01"
        assert kwargs["params"]["to"] == "2024-12-31"

    def test_empty_response(self):
        adapter, _ = _make_adapter({})
        assert adapter.get_news() == []

    def test_non_dict_response(self):
        adapter, _ = _make_adapter("not a dict")
        assert adapter.get_news() == []

    def test_exception_returns_empty(self):
        adapter, client = _make_adapter()
        client.get.side_effect = RuntimeError("network error")
        assert adapter.get_news() == []

    def test_parses_news_items(self):
        raw = {"data": {"section": [{"headline": "A", "summary": "B", "source": "S"}]}}
        adapter, _ = _make_adapter(raw)
        result = adapter.get_news()
        assert len(result) == 1
        assert result[0].headline == "A"
        assert result[0].summary == "B"
        assert result[0].source == "S"

    def test_data_as_list(self):
        raw = {"data": [{"headline": "X"}]}
        adapter, _ = _make_adapter(raw)
        assert len(adapter.get_news()) == 1

    def test_body_as_list(self):
        adapter, _ = _make_adapter([{"headline": "Y"}])
        assert len(adapter.get_news()) == 1

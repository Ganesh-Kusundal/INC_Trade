"""Tests for Upstox news adapter and client."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from brokers.upstox.news.adapter import UpstoxNewsAdapter
from brokers.upstox.news.client import UpstoxNewsClient


@pytest.fixture
def mock_http() -> MagicMock:
    http = MagicMock()
    return http


@pytest.fixture
def mock_urls() -> MagicMock:
    urls = MagicMock()
    urls.news_url.return_value = "https://api.upstox.com/v2/news"
    return urls


@pytest.fixture
def client(mock_http: MagicMock, mock_urls: MagicMock) -> UpstoxNewsClient:
    return UpstoxNewsClient(mock_http, mock_urls)


@pytest.fixture
def adapter(client: UpstoxNewsClient) -> UpstoxNewsAdapter:
    return UpstoxNewsAdapter(client)


class TestUpstoxNewsClient:
    def test_get_news_returns_list(self, client: UpstoxNewsClient, mock_http: MagicMock) -> None:
        mock_http.get_json.return_value = [
            {"headline": "Test news", "source": "Test", "timestamp": "2026-01-01"},
            {"headline": "Test news 2", "source": "Test", "timestamp": "2026-01-02"},
        ]
        result = client.get_news()
        assert len(result) == 2
        assert result[0]["headline"] == "Test news"

    def test_get_news_with_symbol(self, client: UpstoxNewsClient, mock_http: MagicMock) -> None:
        mock_http.get_json.return_value = [{"headline": "Reliance news"}]
        result = client.get_news(symbol="RELIANCE")
        assert len(result) == 1
        mock_http.get_json.assert_called_once()
        call_args = mock_http.get_json.call_args
        assert call_args[1]["params"]["symbol"] == "RELIANCE"

    def test_get_news_with_dates(self, client: UpstoxNewsClient, mock_http: MagicMock) -> None:
        mock_http.get_json.return_value = []
        result = client.get_news(from_date="2026-01-01", to_date="2026-01-31")
        assert result == []
        call_args = mock_http.get_json.call_args
        assert call_args[1]["params"]["from"] == "2026-01-01"
        assert call_args[1]["params"]["to"] == "2026-01-31"

    def test_get_news_dict_response(self, client: UpstoxNewsClient, mock_http: MagicMock) -> None:
        mock_http.get_json.return_value = {"data": [{"headline": "News in data"}]}
        result = client.get_news()
        assert len(result) == 1
        assert result[0]["headline"] == "News in data"

    def test_get_news_dict_no_data(self, client: UpstoxNewsClient, mock_http: MagicMock) -> None:
        mock_http.get_json.return_value = {"message": "no data"}
        result = client.get_news()
        assert result == []

    def test_get_news_non_list_non_dict(
        self, client: UpstoxNewsClient, mock_http: MagicMock
    ) -> None:
        mock_http.get_json.return_value = "unexpected"
        result = client.get_news()
        assert result == []

    def test_get_news_for_instruments(self, client: UpstoxNewsClient, mock_http: MagicMock) -> None:
        mock_http.get_json.return_value = {"data": []}
        client.get_news_for_instruments(["NSE_EQ|INE002A01018"])
        assert mock_http.get_json.called

    def test_get_news_for_instruments_string_input(
        self, client: UpstoxNewsClient, mock_http: MagicMock
    ) -> None:
        mock_http.get_json.return_value = []
        client.get_news_for_instruments("NSE_EQ|INE002A01018")
        assert mock_http.get_json.called


class TestUpstoxNewsAdapter:
    def test_get_news_delegates(self, adapter: UpstoxNewsAdapter, mock_http: MagicMock) -> None:
        mock_http.get_json.return_value = [{"headline": "Test"}]
        result = adapter.get_news()
        assert len(result) == 1

    def test_get_news_with_filters(self, adapter: UpstoxNewsAdapter, mock_http: MagicMock) -> None:
        mock_http.get_json.return_value = [{"headline": "Reliance"}]
        result = adapter.get_news(symbol="RELIANCE", from_date="2026-01-01")
        assert len(result) == 1
        call_args = mock_http.get_json.call_args
        assert call_args[1]["params"]["symbol"] == "RELIANCE"
        assert call_args[1]["params"]["from"] == "2026-01-01"


class TestNewsCLI:
    def test_news_no_broker(self) -> None:
        from unittest.mock import MagicMock

        from rich.console import Console

        from cli.commands.news import run

        broker_service = MagicMock()
        broker_service.active_broker = None
        console = Console(record=True)
        run([], broker_service, console)
        output = console.export_text()
        assert "No active broker" in output

    def test_news_no_news_support(self) -> None:
        from unittest.mock import MagicMock

        from rich.console import Console

        from cli.commands.news import run

        broker_service = MagicMock()
        broker_service.active_broker = MagicMock(spec=[])  # No news attribute
        console = Console(record=True)
        run([], broker_service, console)
        output = console.export_text()
        assert "does not support news" in output

    def test_news_no_items(self) -> None:
        from unittest.mock import MagicMock

        from rich.console import Console

        from cli.commands.news import run

        broker = MagicMock()
        broker.news.get_news.return_value = []
        broker_service = MagicMock()
        broker_service.active_broker = broker
        console = Console(record=True)
        run([], broker_service, console)
        output = console.export_text()
        assert "No news items found" in output

    def test_news_with_items(self) -> None:
        from unittest.mock import MagicMock

        from rich.console import Console

        from cli.commands.news import run

        broker = MagicMock()
        broker.news.get_news.return_value = [
            {"headline": "Test headline", "source": "TestSource", "timestamp": "2026-01-01 10:00"},
            {
                "headline": "Another headline",
                "source": "TestSource",
                "timestamp": "2026-01-01 11:00",
            },
        ]
        broker_service = MagicMock()
        broker_service.active_broker = broker
        console = Console(record=True)
        run([], broker_service, console)
        output = console.export_text()
        assert "Test headline" in output
        assert "Another headline" in output

    def test_news_with_symbol_filter(self) -> None:
        from unittest.mock import MagicMock

        from rich.console import Console

        from cli.commands.news import run

        broker = MagicMock()
        broker.news.get_news.return_value = [{"headline": "Reliance news"}]
        broker_service = MagicMock()
        broker_service.active_broker = broker
        console = Console(record=True)
        run(["RELIANCE"], broker_service, console)
        output = console.export_text()
        assert "Reliance news" in output
        broker.news.get_news.assert_called_once_with(symbol="RELIANCE")

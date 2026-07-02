"""Tests for Upstox newly wired adapters: IPO, Payments, Mutual Funds, Fundamentals."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_http_client():
    client = MagicMock()
    return client


@pytest.fixture
def mock_url_resolver():
    resolver = MagicMock()
    resolver.ipo_url.return_value = "https://api.upstox.com/v2/ipo"
    resolver.payments_url.return_value = "https://api.upstox.com/v2/payments"
    resolver.mutual_funds_url.return_value = "https://api.upstox.com/v2/mutual-funds"
    resolver.fundamentals_url.return_value = "https://api.upstox.com/v2/fundamentals"
    return resolver


# IPO Tests


class TestUpstoxIpoAdapter:
    def test_get_ipos_returns_list(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.ipo.adapter import UpstoxIpoAdapter
        from brokers.upstox.ipo.client import UpstoxIpoClient

        mock_http_client.get_json.return_value = {
            "status": "success",
            "data": [
                {"name": "IPO1", "status": "open"},
                {"name": "IPO2", "status": "open"},
            ],
        }

        client = UpstoxIpoClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxIpoAdapter(client)
        result = adapter.get_ipos(status="open")

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["name"] == "IPO1"
        mock_http_client.get_json.assert_called_once()

    def test_get_ipos_empty_response(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.ipo.adapter import UpstoxIpoAdapter
        from brokers.upstox.ipo.client import UpstoxIpoClient

        mock_http_client.get_json.return_value = {"status": "success", "data": []}

        client = UpstoxIpoClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxIpoAdapter(client)
        result = adapter.get_ipos()

        assert isinstance(result, list)
        assert len(result) == 0


# Payments Tests


class TestUpstoxPaymentsAdapter:
    def test_initiate_payout(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.payments.adapter import UpstoxPaymentsAdapter
        from brokers.upstox.payments.client import UpstoxPaymentsClient

        mock_http_client.post_json.return_value = {
            "status": "success",
            "data": {"payout_id": "PAY123"},
        }

        client = UpstoxPaymentsClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxPaymentsAdapter(client)
        result = adapter.initiate_payout({"amount": 1000})

        assert result["status"] == "success"
        assert result["data"]["payout_id"] == "PAY123"

    def test_get_payouts(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.payments.adapter import UpstoxPaymentsAdapter
        from brokers.upstox.payments.client import UpstoxPaymentsClient

        mock_http_client.get_json.return_value = {
            "status": "success",
            "data": [{"payout_id": "PAY123", "amount": 1000}],
        }

        client = UpstoxPaymentsClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxPaymentsAdapter(client)
        result = adapter.get_payouts()

        assert isinstance(result, list)
        assert len(result) == 1

    def test_cancel_payout(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.payments.adapter import UpstoxPaymentsAdapter
        from brokers.upstox.payments.client import UpstoxPaymentsClient

        mock_http_client.delete_json.return_value = {"status": "success"}

        client = UpstoxPaymentsClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxPaymentsAdapter(client)
        result = adapter.cancel_payout("PAY123")

        assert result["status"] == "success"


# Mutual Funds Tests


class TestUpstoxMutualFundsAdapter:
    def test_get_holdings(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.mutual_funds.adapter import UpstoxMutualFundsAdapter
        from brokers.upstox.mutual_funds.client import UpstoxMutualFundsClient

        mock_http_client.get_json.return_value = {
            "status": "success",
            "data": [
                {"fund_name": "HDFC Equity Fund", "units": 100.5},
            ],
        }

        client = UpstoxMutualFundsClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxMutualFundsAdapter(client)
        result = adapter.get_holdings()

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["fund_name"] == "HDFC Equity Fund"

    def test_place_order(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.mutual_funds.adapter import UpstoxMutualFundsAdapter
        from brokers.upstox.mutual_funds.client import UpstoxMutualFundsClient

        mock_http_client.post_json.return_value = {
            "status": "success",
            "data": {"order_id": "MF123"},
        }

        client = UpstoxMutualFundsClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxMutualFundsAdapter(client)
        result = adapter.place_order({"fund_name": "HDFC Equity Fund", "amount": 5000})

        assert result["status"] == "success"
        assert result["data"]["order_id"] == "MF123"


# Fundamentals Tests


class TestUpstoxFundamentalsAdapter:
    def test_get_pnl(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.fundamentals.adapter import UpstoxFundamentalsAdapter
        from brokers.upstox.fundamentals.client import UpstoxFundamentalsClient

        mock_http_client.get_json.return_value = {
            "status": "success",
            "data": {
                "isin": "INE002A01018",
                "revenue": 100000,
                "profit": 25000,
            },
        }

        client = UpstoxFundamentalsClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxFundamentalsAdapter(client)
        result = adapter.get_pnl("INE002A01018")

        assert result["status"] == "success"
        assert result["data"]["isin"] == "INE002A01018"

    def test_get_ratios(self, mock_http_client, mock_url_resolver):
        from brokers.upstox.fundamentals.adapter import UpstoxFundamentalsAdapter
        from brokers.upstox.fundamentals.client import UpstoxFundamentalsClient

        mock_http_client.get_json.return_value = {
            "status": "success",
            "data": {
                "pe_ratio": 25.5,
                "pb_ratio": 3.2,
            },
        }

        client = UpstoxFundamentalsClient(mock_http_client, mock_url_resolver)
        adapter = UpstoxFundamentalsAdapter(client)
        result = adapter.get_ratios("INE002A01018")

        assert result["status"] == "success"
        assert result["data"]["pe_ratio"] == 25.5


# Gateway Integration Tests


class TestUpstoxGatewayNewFeatures:
    def _make_mock_broker(self):
        from unittest.mock import MagicMock

        from brokers.upstox.broker import UpstoxBroker

        mock_broker = MagicMock(spec=UpstoxBroker)
        mock_broker.instrument_resolver = MagicMock()
        mock_broker.order_command = MagicMock()
        mock_broker.market_data_v2 = MagicMock()
        mock_broker.market_data_v3 = MagicMock()
        mock_broker.historical_v2 = MagicMock()
        return mock_broker

    def test_gateway_ipo_property(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = self._make_mock_broker()
        mock_broker.ipo = MagicMock()

        gateway = UpstoxBrokerGateway(mock_broker)
        assert gateway.extended is not None
        assert hasattr(gateway.extended, "get_ipos")

    def test_gateway_payments_property(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = self._make_mock_broker()
        mock_broker.payments = MagicMock()

        gateway = UpstoxBrokerGateway(mock_broker)
        assert gateway.extended is not None
        assert hasattr(gateway.extended, "initiate_payout")

    def test_gateway_mutual_funds_property(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = self._make_mock_broker()
        mock_broker.mutual_funds = MagicMock()

        gateway = UpstoxBrokerGateway(mock_broker)
        assert gateway.extended is not None
        assert hasattr(gateway.extended, "get_mutual_fund_holdings")

    def test_gateway_fundamentals_property(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = self._make_mock_broker()
        mock_broker.fundamentals = MagicMock()

        gateway = UpstoxBrokerGateway(mock_broker)
        assert gateway.extended is not None
        assert hasattr(gateway.extended, "get_pnl")

    def test_gateway_capabilities_includes_new_features(self):
        from brokers.upstox.gateway import UpstoxBrokerGateway

        mock_broker = self._make_mock_broker()
        mock_broker.portfolio = MagicMock()
        mock_broker.portfolio.get_fund_limits.return_value = MagicMock()
        mock_broker.portfolio.get_positions.return_value = []
        mock_broker.portfolio.get_holdings.return_value = []
        mock_broker.instrument_resolver = MagicMock()
        mock_broker.order_command = MagicMock()  # Required by gateway __init__

        gateway = UpstoxBrokerGateway(mock_broker)
        caps = gateway.capabilities()

        assert caps.supports_news is True
        assert caps.supports_fundamentals is True
        assert caps.supports_forever_order is True
        assert caps.supports_portfolio_stream is True

"""Failure-path tests for Upstox adapters (TEST-01, TEST-02).

These tests verify that adapters gracefully handle:
- Network failures (connection errors, timeouts)
- API errors (4xx, 5xx responses)
- Invalid responses (malformed JSON, missing fields)
- Empty responses

All tests use mocks to simulate failure scenarios without requiring
live API connections.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from brokers.upstox.auth.exceptions import UpstoxApiError
from brokers.upstox.fundamentals.adapter import UpstoxFundamentalsAdapter
from brokers.upstox.fundamentals.client import UpstoxFundamentalsClient
from brokers.upstox.ipo.adapter import UpstoxIpoAdapter
from brokers.upstox.ipo.client import UpstoxIpoClient
from brokers.upstox.mutual_funds.adapter import UpstoxMutualFundsAdapter
from brokers.upstox.mutual_funds.client import UpstoxMutualFundsClient
from brokers.upstox.payments.adapter import UpstoxPaymentsAdapter
from brokers.upstox.payments.client import UpstoxPaymentsClient


class TestIpoAdapterFailures:
    """Verify IPO adapter handles failures gracefully."""

    def test_get_ipos_network_error(self):
        """Network error should raise UpstoxApiError."""
        mock_client = Mock()
        mock_client.get_ipo_data.side_effect = ConnectionError("Network unreachable")

        adapter = UpstoxIpoAdapter(mock_client)

        with pytest.raises((ConnectionError, UpstoxApiError)):
            adapter.get_ipos()

    def test_get_ipos_api_error(self):
        """API error (500) should raise UpstoxApiError."""
        mock_client = Mock()
        mock_client.get_ipo_data.side_effect = UpstoxApiError(
            "Internal server error", status_code=500
        )

        adapter = UpstoxIpoAdapter(mock_client)

        with pytest.raises(UpstoxApiError) as exc_info:
            adapter.get_ipos()

        assert exc_info.value.status_code == 500

    def test_get_ipos_empty_response(self):
        """Empty list should be returned as-is."""
        mock_client = Mock()
        mock_client.get_ipo_data.return_value = []

        adapter = UpstoxIpoAdapter(mock_client)
        result = adapter.get_ipos()

        assert result == []

    def test_get_ipos_malformed_response(self):
        """Malformed response should be passed through (adapter is thin wrapper)."""
        mock_client = Mock()
        mock_client.get_ipo_data.return_value = [{"invalid": "data"}]

        adapter = UpstoxIpoAdapter(mock_client)
        result = adapter.get_ipos()

        assert len(result) == 1
        assert result[0] == {"invalid": "data"}


class TestPaymentsAdapterFailures:
    """Verify Payments adapter handles failures gracefully."""

    def test_initiate_payout_network_error(self):
        """Network error should propagate."""
        mock_client = Mock(spec=UpstoxPaymentsClient)
        mock_client.initiate_payout.side_effect = ConnectionError("Timeout")

        adapter = UpstoxPaymentsAdapter(mock_client)

        with pytest.raises(ConnectionError):
            adapter.initiate_payout({"amount": 1000})

    def test_initiate_payout_api_error(self):
        """API error (400) should raise UpstoxApiError."""
        mock_client = Mock(spec=UpstoxPaymentsClient)
        mock_client.initiate_payout.side_effect = UpstoxApiError("Invalid request", status_code=400)

        adapter = UpstoxPaymentsAdapter(mock_client)

        with pytest.raises(UpstoxApiError) as exc_info:
            adapter.initiate_payout({"amount": 1000})

        assert exc_info.value.status_code == 400

    def test_get_payouts_empty(self):
        """Empty payout list should work."""
        mock_client = Mock(spec=UpstoxPaymentsClient)
        mock_client.get_payouts.return_value = []

        adapter = UpstoxPaymentsAdapter(mock_client)
        result = adapter.get_payouts()

        assert result == []

    def test_modify_payout_not_found(self):
        """Modifying non-existent payout should raise error."""
        mock_client = Mock(spec=UpstoxPaymentsClient)
        mock_client.modify_payout.side_effect = UpstoxApiError("Payout not found", status_code=404)

        adapter = UpstoxPaymentsAdapter(mock_client)

        with pytest.raises(UpstoxApiError) as exc_info:
            adapter.modify_payout("invalid-id", {})

        assert exc_info.value.status_code == 404

    def test_cancel_payout_already_processed(self):
        """Cancelling processed payout should fail."""
        mock_client = Mock(spec=UpstoxPaymentsClient)
        mock_client.cancel_payout.side_effect = UpstoxApiError(
            "Payout already processed", status_code=409
        )

        adapter = UpstoxPaymentsAdapter(mock_client)

        with pytest.raises(UpstoxApiError) as exc_info:
            adapter.cancel_payout("processed-id")

        assert exc_info.value.status_code == 409


class TestMutualFundsAdapterFailures:
    """Verify Mutual Funds adapter handles failures gracefully."""

    def test_get_holdings_network_error(self):
        """Network error should propagate."""
        mock_client = Mock(spec=UpstoxMutualFundsClient)
        mock_client.get_holdings.side_effect = ConnectionError("DNS resolution failed")

        adapter = UpstoxMutualFundsAdapter(mock_client)

        with pytest.raises(ConnectionError):
            adapter.get_holdings()

    def test_get_holdings_api_error(self):
        """API error (503) should raise UpstoxApiError."""
        mock_client = Mock(spec=UpstoxMutualFundsClient)
        mock_client.get_holdings.side_effect = UpstoxApiError(
            "Service unavailable", status_code=503
        )

        adapter = UpstoxMutualFundsAdapter(mock_client)

        with pytest.raises(UpstoxApiError) as exc_info:
            adapter.get_holdings()

        assert exc_info.value.status_code == 503

    def test_place_order_validation_error(self):
        """Invalid order payload should raise API error."""
        mock_client = Mock(spec=UpstoxMutualFundsClient)
        mock_client.place_order.side_effect = UpstoxApiError("Invalid scheme code", status_code=400)

        adapter = UpstoxMutualFundsAdapter(mock_client)

        with pytest.raises(UpstoxApiError) as exc_info:
            adapter.place_order({"scheme": "INVALID"})

        assert exc_info.value.status_code == 400

    def test_place_order_success(self):
        """Successful order should return response."""
        mock_client = Mock(spec=UpstoxMutualFundsClient)
        mock_client.place_order.return_value = {"status": "success", "data": {"order_id": "MF-123"}}

        adapter = UpstoxMutualFundsAdapter(mock_client)
        result = adapter.place_order({"scheme": "INF123"})

        assert result["status"] == "success"
        assert result["data"]["order_id"] == "MF-123"


class TestFundamentalsAdapterFailures:
    """Verify Fundamentals adapter handles failures gracefully."""

    def test_get_pnl_invalid_isin(self):
        """Invalid ISIN should raise API error."""
        mock_client = Mock(spec=UpstoxFundamentalsClient)
        mock_client.get_pnl.side_effect = UpstoxApiError("Invalid ISIN format", status_code=400)

        adapter = UpstoxFundamentalsAdapter(mock_client)

        with pytest.raises(UpstoxApiError) as exc_info:
            adapter.get_pnl("INVALID")

        assert exc_info.value.status_code == 400

    def test_get_balance_sheet_not_found(self):
        """Non-existent ISIN should raise error."""
        mock_client = Mock(spec=UpstoxFundamentalsClient)
        mock_client.get_balance_sheet.side_effect = UpstoxApiError(
            "No data available", status_code=404
        )

        adapter = UpstoxFundamentalsAdapter(mock_client)

        with pytest.raises(UpstoxApiError) as exc_info:
            adapter.get_balance_sheet("INE999999999")

        assert exc_info.value.status_code == 404

    def test_get_cash_flow_timeout(self):
        """Timeout should raise appropriate error."""
        mock_client = Mock(spec=UpstoxFundamentalsClient)
        mock_client.get_cash_flow.side_effect = TimeoutError("Request timed out")

        adapter = UpstoxFundamentalsAdapter(mock_client)

        with pytest.raises(TimeoutError):
            adapter.get_cash_flow("INE002A01018")

    def test_get_ratios_empty_response(self):
        """Empty ratios should be returned as-is."""
        mock_client = Mock(spec=UpstoxFundamentalsClient)
        mock_client.get_ratios.return_value = {}

        adapter = UpstoxFundamentalsAdapter(mock_client)
        result = adapter.get_ratios("INE002A01018")

        assert result == {}

    def test_get_pnl_success(self):
        """Successful PnL retrieval should work."""
        mock_client = Mock(spec=UpstoxFundamentalsClient)
        mock_client.get_pnl.return_value = {
            "isin": "INE002A01018",
            "pnl_data": {"revenue": 1000000},
        }

        adapter = UpstoxFundamentalsAdapter(mock_client)
        result = adapter.get_pnl("INE002A01018")

        assert result["isin"] == "INE002A01018"
        assert "pnl_data" in result


class TestAdapterErrorPropagation:
    """Verify errors propagate correctly through adapter chain."""

    def test_ipo_client_http_error(self):
        """IPO client should raise UpstoxApiError on HTTP error."""
        mock_http = Mock()
        mock_http.get_json.side_effect = UpstoxApiError("Rate limit exceeded", status_code=429)

        client = UpstoxIpoClient(mock_http, Mock())

        with pytest.raises(UpstoxApiError) as exc_info:
            client.get_ipo_data()

        assert exc_info.value.status_code == 429

    def test_payments_client_http_error(self):
        """Payments client should raise UpstoxApiError on HTTP error."""
        mock_http = Mock()
        mock_http.post_json.side_effect = UpstoxApiError("Unauthorized", status_code=401)

        client = UpstoxPaymentsClient(mock_http, Mock())

        with pytest.raises(UpstoxApiError) as exc_info:
            client.initiate_payout({})

        assert exc_info.value.status_code == 401

    def test_mutual_funds_client_http_error(self):
        """Mutual funds client should raise UpstoxApiError on HTTP error."""
        mock_http = Mock()
        mock_http.post_json.side_effect = UpstoxApiError("Bad gateway", status_code=502)

        client = UpstoxMutualFundsClient(mock_http, Mock())

        with pytest.raises(UpstoxApiError) as exc_info:
            client.place_order({})

        assert exc_info.value.status_code == 502

    def test_fundamentals_client_http_error(self):
        """Fundamentals client should raise UpstoxApiError on HTTP error."""
        mock_http = Mock()
        mock_http.get_json.side_effect = UpstoxApiError("Gateway timeout", status_code=504)

        client = UpstoxFundamentalsClient(mock_http, Mock())

        with pytest.raises(UpstoxApiError) as exc_info:
            client.get_pnl("INE002A01018")

        assert exc_info.value.status_code == 504

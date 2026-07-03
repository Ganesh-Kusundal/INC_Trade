"""Unit tests for UpstoxExtended."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from brokers.adapters.upstox.extended import UpstoxExtended


class TestUpstoxExtended:
    def test_get_user_profile(self):
        client = MagicMock()
        client.get.return_value = {"data": {"name": "test"}}
        ext = UpstoxExtended(client)
        profile = ext.get_user_profile()
        assert profile.name == "test"

    def test_get_ipos(self):
        client = MagicMock()
        client.get.return_value = {"data": [{"name": "IPO1"}]}
        ext = UpstoxExtended(client)
        ipos = ext.get_ipos()
        assert len(ipos) == 1


class TestGetUserProfile:
    def test_get_user_profile_calls_correct_endpoint(self):
        client = MagicMock()
        client.get.return_value = {"data": {"user_id": "U001", "name": "Test User"}}
        ext = UpstoxExtended(client)
        ext.get_user_profile()
        call_args = client.get.call_args
        endpoint = call_args[0][0]
        assert "profile" in endpoint.lower()

    def test_get_user_profile_returns_user_profile(self):
        client = MagicMock()
        client.get.return_value = {
            "data": {
                "user_id": "U001",
                "name": "Test User",
                "email": "test@example.com",
                "mobile": "9999999999",
                "broker": "upstox",
            }
        }
        ext = UpstoxExtended(client)
        profile = ext.get_user_profile()
        assert profile.user_id == "U001"
        assert profile.name == "Test User"
        assert profile.email == "test@example.com"
        assert profile.mobile == "9999999999"
        assert profile.broker == "upstox"

    def test_get_user_profile_empty_response(self):
        client = MagicMock()
        client.get.return_value = {}
        ext = UpstoxExtended(client)
        profile = ext.get_user_profile()
        assert profile.user_id == ""
        assert profile.name == ""

    def test_get_user_profile_non_dict_data(self):
        client = MagicMock()
        client.get.return_value = "unexpected"
        ext = UpstoxExtended(client)
        profile = ext.get_user_profile()
        assert profile.user_id == ""


class TestGetIpos:
    def test_get_ipos_calls_correct_endpoint(self):
        client = MagicMock()
        client.get.return_value = {"data": []}
        ext = UpstoxExtended(client)
        ext.get_ipos()
        call_args = client.get.call_args
        endpoint = call_args[0][0]
        assert "ipo" in endpoint.lower()

    def test_get_ipos_passes_status_param(self):
        client = MagicMock()
        client.get.return_value = {"data": []}
        ext = UpstoxExtended(client)
        ext.get_ipos(status="closed")
        call_kwargs = client.get.call_args[1]
        assert call_kwargs["params"]["status"] == "closed"

    def test_get_ipos_returns_list_of_ipo_info(self):
        client = MagicMock()
        client.get.return_value = {
            "data": [
                {
                    "company_name": "Acme Corp",
                    "symbol": "ACME",
                    "status": "open",
                    "price_min": "100",
                    "price_max": "150",
                },
                {
                    "company_name": "Beta Inc",
                    "symbol": "BETA",
                    "status": "open",
                    "price_min": "200",
                    "price_max": "250",
                },
            ]
        }
        ext = UpstoxExtended(client)
        ipos = ext.get_ipos()
        assert len(ipos) == 2
        assert ipos[0].company_name == "Acme Corp"
        assert ipos[0].symbol == "ACME"
        assert ipos[0].price_min == Decimal("100")
        assert ipos[1].company_name == "Beta Inc"

    def test_get_ipos_empty_response(self):
        client = MagicMock()
        client.get.return_value = {"data": []}
        ext = UpstoxExtended(client)
        ipos = ext.get_ipos()
        assert ipos == []

    def test_get_ipos_non_list_data(self):
        client = MagicMock()
        client.get.return_value = {"data": "not a list"}
        ext = UpstoxExtended(client)
        ipos = ext.get_ipos()
        assert ipos == []

    def test_get_ipos_filters_non_dict_items(self):
        client = MagicMock()
        client.get.return_value = {
            "data": [
                {"company_name": "Good IPO", "symbol": "GOOD"},
                "bad item",
                None,
                42,
            ]
        }
        ext = UpstoxExtended(client)
        ipos = ext.get_ipos()
        assert len(ipos) == 1
        assert ipos[0].company_name == "Good IPO"


class TestGetMutualFundHoldings:
    def test_get_mutual_fund_holdings_calls_correct_endpoint(self):
        client = MagicMock()
        client.get.return_value = {"data": []}
        ext = UpstoxExtended(client)
        ext.get_mutual_fund_holdings()
        call_args = client.get.call_args
        endpoint = call_args[0][0]
        assert "mutual" in endpoint.lower() or "fund" in endpoint.lower()

    def test_get_mutual_fund_holdings_returns_list(self):
        client = MagicMock()
        client.get.return_value = {
            "data": [
                {
                    "name": "HDFC Midcap Fund",
                    "units": "100.5",
                    "current_value": "15000",
                },
                {
                    "name": "ICICI Pru Tech Fund",
                    "units": "50.25",
                    "current_value": "8000",
                },
            ]
        }
        ext = UpstoxExtended(client)
        holdings = ext.get_mutual_fund_holdings()
        assert len(holdings) == 2
        assert holdings[0].name == "HDFC Midcap Fund"
        assert holdings[0].units == Decimal("100.5")
        assert holdings[0].current_value == Decimal("15000")
        assert holdings[1].name == "ICICI Pru Tech Fund"

    def test_get_mutual_fund_holdings_empty_response(self):
        client = MagicMock()
        client.get.return_value = {"data": []}
        ext = UpstoxExtended(client)
        holdings = ext.get_mutual_fund_holdings()
        assert holdings == []

    def test_get_mutual_fund_holdings_non_dict_data(self):
        client = MagicMock()
        client.get.return_value = "unexpected"
        ext = UpstoxExtended(client)
        holdings = ext.get_mutual_fund_holdings()
        assert holdings == []


class TestConvertPosition:
    def test_convert_position_calls_correct_endpoint(self):
        client = MagicMock()
        client.post.return_value = {"status": "success"}
        ext = UpstoxExtended(client)
        ext.convert_position({"symbol": "RELIANCE", "quantity": 10})
        call_args = client.post.call_args
        endpoint = call_args[0][0]
        assert "convert" in endpoint.lower() or "position" in endpoint.lower()

    def test_convert_position_passes_payload(self):
        client = MagicMock()
        client.post.return_value = {"status": "success"}
        ext = UpstoxExtended(client)
        payload = {"symbol": "RELIANCE", "quantity": 10, "exchange": "NSE_EQ"}
        ext.convert_position(payload)
        call_kwargs = client.post.call_args[1]
        assert call_kwargs.get("json") == payload

    def test_convert_position_returns_response(self):
        client = MagicMock()
        client.post.return_value = {"status": "success", "data": {"converted": True}}
        ext = UpstoxExtended(client)
        result = ext.convert_position({"symbol": "RELIANCE"})
        assert result == {"status": "success", "data": {"converted": True}}

"""Tests for Dhan Phase 3 adapters: conditional triggers, EDIS, MTF, ledger, alerts."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import Mock

from brokers.domain.enums import OrderType, Side

from brokers.adapters.dhan.alerts import DhanAlerts
from brokers.adapters.dhan.conditional_triggers import DhanConditionalTriggers
from brokers.adapters.dhan.edis import DhanEDIS
from brokers.adapters.dhan.ledger import DhanLedger
from brokers.adapters.dhan.mtf import DhanMTF

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_ref():
    ref = Mock()
    ref.exchange_segment = "NSE_EQ"
    ref.security_id_str.return_value = "11536"
    return ref


def _mock_resolver():
    resolver = Mock()
    resolver.resolve.return_value = _mock_ref()
    return resolver


def _mock_client():
    client = Mock()
    client.client_id = "TEST_CLIENT"
    return client


# ---------------------------------------------------------------------------
# MODULE 1: conditional_triggers.py
# ---------------------------------------------------------------------------

class TestConditionalTriggers:
    def test_place_conditional_order(self):
        client = _mock_client()
        resolver = _mock_resolver()
        adapter = DhanConditionalTriggers(client, resolver)

        client.post.return_value = {"status": "success", "data": {"orderId": "GT123"}}

        result = adapter.place_conditional_order(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            order_type=OrderType.LIMIT,
            price=Decimal("2500.00"),
            trigger_price=Decimal("2400.00"),
        )

        resolver.resolve.assert_called_once_with("RELIANCE", "NSE")
        client.post.assert_called_once()
        call_args = client.post.call_args
        assert call_args[0][0] == "/conditionalOrders"
        payload = call_args[1]["json"]
        assert payload["dhanClientId"] == "TEST_CLIENT"
        assert payload["transactionType"] == 1
        assert payload["exchangeSegment"] == "NSE_EQ"
        assert payload["securityId"] == "11536"
        assert payload["quantity"] == 10
        assert payload["productType"] == "INTRADAY"
        assert result == {"status": "success", "data": {"orderId": "GT123"}}

    def test_cancel_conditional_order(self):
        client = _mock_client()
        resolver = _mock_resolver()
        adapter = DhanConditionalTriggers(client, resolver)

        client.delete.return_value = {"status": "success"}

        result = adapter.cancel_conditional_order("GT123")

        client.delete.assert_called_once_with("/conditionalOrders/GT123")
        assert result == {"status": "success"}

    def test_get_conditional_orders(self):
        client = _mock_client()
        resolver = _mock_resolver()
        adapter = DhanConditionalTriggers(client, resolver)

        orders = [{"orderId": "GT1"}, {"orderId": "GT2"}]
        client.get.return_value = {"status": "success", "data": orders}

        result = adapter.get_conditional_orders()

        client.get.assert_called_once_with("/conditionalOrders")
        assert result == orders

    def test_get_conditional_orders_empty(self):
        client = _mock_client()
        resolver = _mock_resolver()
        adapter = DhanConditionalTriggers(client, resolver)

        client.get.return_value = {"status": "success"}

        result = adapter.get_conditional_orders()
        assert result == []

    def test_get_conditional_orders_non_dict_response(self):
        client = _mock_client()
        resolver = _mock_resolver()
        adapter = DhanConditionalTriggers(client, resolver)

        client.get.return_value = "error"

        result = adapter.get_conditional_orders()
        assert result == []


# ---------------------------------------------------------------------------
# MODULE 2: edis.py
# ---------------------------------------------------------------------------

class TestEDIS:
    def test_get_tpin_status(self):
        client = _mock_client()
        adapter = DhanEDIS(client)

        client.get.return_value = {"tpinStatus": "ACTIVE", "validTill": "2026-12-31"}

        result = adapter.get_tpin_status()

        client.get.assert_called_once_with("/edis/tpinStatus")
        assert result == {"tpinStatus": "ACTIVE", "validTill": "2026-12-31"}

    def test_generate_tpin(self):
        client = _mock_client()
        adapter = DhanEDIS(client)

        client.get.return_value = {"status": "success", "remarks": "TPIN sent"}

        result = adapter.generate_tpin()

        client.get.assert_called_once_with("/edis/generateTpin")
        assert result == {"status": "success", "remarks": "TPIN sent"}

    def test_get_edis_form(self):
        client = _mock_client()
        adapter = DhanEDIS(client)

        client.post.return_value = {"formUrl": "https://cdsl.example/auth", "status": "success"}

        result = adapter.get_edis_form(isin="INE002A01018", qty=10, exchange="NSE")

        client.post.assert_called_once()
        call_args = client.post.call_args
        assert call_args[0][0] == "/edis/form"
        assert call_args[1]["json"] == {"isin": "INE002A01018", "qty": 10, "exchange": "NSE"}
        assert result["status"] == "success"

    def test_get_tpin_status_exception(self):
        client = _mock_client()
        adapter = DhanEDIS(client)

        client.get.side_effect = Exception("network error")

        result = adapter.get_tpin_status()
        assert "error" in result
        assert "network error" in result["error"]

    def test_generate_tpin_exception(self):
        client = _mock_client()
        adapter = DhanEDIS(client)

        client.get.side_effect = Exception("timeout")

        result = adapter.generate_tpin()
        assert "error" in result
        assert "timeout" in result["error"]

    def test_get_edis_form_exception(self):
        client = _mock_client()
        adapter = DhanEDIS(client)

        client.post.side_effect = Exception("conn refused")

        result = adapter.get_edis_form(isin="INE002A01018", qty=10)
        assert "error" in result
        assert "conn refused" in result["error"]


# ---------------------------------------------------------------------------
# MODULE 3: mtf.py
# ---------------------------------------------------------------------------

class TestMTF:
    def test_place_mtf_order(self):
        client = _mock_client()
        resolver = _mock_resolver()
        adapter = DhanMTF(client, resolver)

        client.post.return_value = {"status": "success", "data": {"orderId": "MTF456"}}

        result = adapter.place_mtf_order(
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=5,
        )

        resolver.resolve.assert_called_once_with("RELIANCE", "NSE")
        client.post.assert_called_once()
        payload = client.post.call_args[1]["json"]
        assert payload["productType"] == "MTF"
        assert payload["dhanClientId"] == "TEST_CLIENT"
        assert payload["transactionType"] == 1
        assert payload["quantity"] == 5
        assert result == {"status": "success", "data": {"orderId": "MTF456"}}

    def test_place_mtf_order_with_limit_price(self):
        client = _mock_client()
        resolver = _mock_resolver()
        adapter = DhanMTF(client, resolver)

        client.post.return_value = {"status": "success", "data": {"orderId": "MTF789"}}

        result = adapter.place_mtf_order(
            symbol="INFY",
            exchange="NSE",
            side=Side.SELL,
            quantity=20,
            order_type=OrderType.LIMIT,
            price=Decimal("1450.00"),
        )

        payload = client.post.call_args[1]["json"]
        assert payload["productType"] == "MTF"
        assert payload["transactionType"] == 2
        assert payload["orderType"] == 2
        assert payload["price"] == 1450.0


# ---------------------------------------------------------------------------
# MODULE 4: ledger.py
# ---------------------------------------------------------------------------

class TestLedger:
    def test_get_ledger(self):
        client = _mock_client()
        adapter = DhanLedger(client)

        ledger_data = [
            {"date": "2026-01-01", "amount": 100.0},
            {"date": "2026-01-02", "amount": -50.0},
        ]
        client.get.return_value = {"status": "success", "data": ledger_data}

        result = adapter.get_ledger("2026-01-01", "2026-01-31")

        client.get.assert_called_once_with("/ledger?fromDate=2026-01-01&toDate=2026-01-31")
        assert result == ledger_data

    def test_get_ledger_empty_response(self):
        client = _mock_client()
        adapter = DhanLedger(client)

        client.get.return_value = {"status": "success", "data": []}

        result = adapter.get_ledger("2026-01-01", "2026-01-31")
        assert result == []

    def test_get_ledger_no_data_key(self):
        client = _mock_client()
        adapter = DhanLedger(client)

        client.get.return_value = {"status": "success"}

        result = adapter.get_ledger("2026-01-01", "2026-01-31")
        assert result == []

    def test_get_ledger_non_dict_response(self):
        client = _mock_client()
        adapter = DhanLedger(client)

        client.get.return_value = "error"

        result = adapter.get_ledger("2026-01-01", "2026-01-31")
        assert result == []

    def test_get_ledger_data_not_list(self):
        client = _mock_client()
        adapter = DhanLedger(client)

        client.get.return_value = {"status": "success", "data": "not a list"}

        result = adapter.get_ledger("2026-01-01", "2026-01-31")
        assert result == []

    def test_get_ledger_exception(self):
        client = _mock_client()
        adapter = DhanLedger(client)

        client.get.side_effect = Exception("timeout")

        result = adapter.get_ledger("2026-01-01", "2026-01-31")
        assert result == []


# ---------------------------------------------------------------------------
# MODULE 5: alerts.py
# ---------------------------------------------------------------------------

class TestAlerts:
    def test_create_alert(self):
        client = _mock_client()
        adapter = DhanAlerts(client)

        client.post.return_value = {"status": "success", "data": {"alertId": "A123"}}

        result = adapter.create_alert(
            symbol="RELIANCE",
            price=2500.0,
            condition="ABOVE",
            exchange_segment="NSE_EQ",
        )

        client.post.assert_called_once()
        call_args = client.post.call_args
        assert call_args[0][0] == "/alerts"
        assert call_args[1]["json"] == {
            "tradingSymbol": "RELIANCE",
            "alertPrice": 2500.0,
            "alertCondition": "ABOVE",
            "exchangeSegment": "NSE_EQ",
        }
        assert result == {"status": "success", "data": {"alertId": "A123"}}

    def test_create_alert_default_segment(self):
        client = _mock_client()
        adapter = DhanAlerts(client)

        client.post.return_value = {"status": "success", "data": {"alertId": "A456"}}

        result = adapter.create_alert(symbol="INFY", price=1400.0, condition="BELOW")

        payload = client.post.call_args[1]["json"]
        assert payload["exchangeSegment"] == "NSE_EQ"

    def test_get_alerts(self):
        client = _mock_client()
        adapter = DhanAlerts(client)

        alerts = [{"alertId": "A1"}, {"alertId": "A2"}]
        client.get.return_value = {"status": "success", "data": alerts}

        result = adapter.get_alerts()

        client.get.assert_called_once_with("/alerts")
        assert result == alerts

    def test_get_alerts_empty(self):
        client = _mock_client()
        adapter = DhanAlerts(client)

        client.get.return_value = {"status": "success"}

        result = adapter.get_alerts()
        assert result == []

    def test_get_alerts_non_dict_response(self):
        client = _mock_client()
        adapter = DhanAlerts(client)

        client.get.return_value = "error"

        result = adapter.get_alerts()
        assert result == []

    def test_delete_alert(self):
        client = _mock_client()
        adapter = DhanAlerts(client)

        client.delete.return_value = {"status": "success"}

        result = adapter.delete_alert("A123")

        client.delete.assert_called_once_with("/alerts/A123")
        assert result == {"status": "success"}

    def test_update_alert(self):
        client = _mock_client()
        adapter = DhanAlerts(client)

        client.put.return_value = {"status": "success"}

        result = adapter.update_alert("A123", price=2600.0, condition="ABOVE")

        client.put.assert_called_once()
        call_args = client.put.call_args
        assert call_args[0][0] == "/alerts/A123"
        assert call_args[1]["json"] == {"alertPrice": 2600.0, "alertCondition": "ABOVE"}
        assert result == {"status": "success"}

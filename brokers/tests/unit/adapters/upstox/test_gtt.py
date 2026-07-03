"""Unit tests for UpstoxGtt."""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.adapters.upstox.gtt import UpstoxGtt


class TestUpstoxGtt:
    def test_place_gtt(self):
        client = MagicMock()
        client.post.return_value = {
            "status": "success",
            "data": {"gtt_order_id": "GTT001"},
        }
        gtt = UpstoxGtt(client)
        resp = gtt.place_gtt({"quantity": 1})
        assert resp.success
        assert resp.order_id == "GTT001"

    def test_cancel_gtt(self):
        client = MagicMock()
        client.delete.return_value = {"status": "success"}
        gtt = UpstoxGtt(client)
        resp = gtt.cancel_gtt("GTT001")
        assert resp.success


class TestPlaceGtt:
    def test_place_gtt_calls_correct_endpoint(self):
        client = MagicMock()
        client.post.return_value = {"status": "success", "data": {"gtt_order_id": "GTT100"}}
        gtt = UpstoxGtt(client)
        gtt.place_gtt({"quantity": 5, "price": 2500})
        call_args = client.post.call_args
        endpoint = call_args[0][0]
        assert "gtt" in endpoint.lower()

    def test_place_gtt_passes_json_payload(self):
        client = MagicMock()
        client.post.return_value = {"data": {"gtt_order_id": "GTT200"}}
        gtt = UpstoxGtt(client)
        payload = {"quantity": 10, "price": 100, "trigger_price": 95}
        gtt.place_gtt(payload)
        call_kwargs = client.post.call_args[1]
        assert call_kwargs.get("json") == payload

    def test_place_gtt_successful_response(self):
        client = MagicMock()
        client.post.return_value = {
            "status": "success",
            "message": "Order placed",
            "data": {"gtt_order_id": "GTT300"},
        }
        gtt = UpstoxGtt(client)
        resp = gtt.place_gtt({"quantity": 1})
        assert resp.success is True
        assert resp.order_id == "GTT300"
        assert resp.message == "Order placed"

    def test_place_gtt_error_response(self):
        client = MagicMock()
        client.post.return_value = {
            "status": "error",
            "message": "Invalid payload",
        }
        gtt = UpstoxGtt(client)
        resp = gtt.place_gtt({"bad": "data"})
        assert resp.success is False
        assert resp.order_id == ""
        assert resp.message == "Invalid payload"

    def test_place_gtt_no_data_field(self):
        client = MagicMock()
        client.post.return_value = {"status": "success"}
        gtt = UpstoxGtt(client)
        resp = gtt.place_gtt({"quantity": 1})
        assert resp.success is False
        assert resp.order_id == ""


class TestModifyGtt:
    def test_modify_gtt_calls_correct_endpoint(self):
        client = MagicMock()
        client.put.return_value = {"status": "success"}
        gtt = UpstoxGtt(client)
        gtt.modify_gtt("GTT001", {"quantity": 20})
        call_args = client.put.call_args
        endpoint = call_args[0][0]
        assert "gtt" in endpoint.lower()
        assert "GTT001" in endpoint

    def test_modify_gtt_passes_payload(self):
        client = MagicMock()
        client.put.return_value = {"status": "success"}
        gtt = UpstoxGtt(client)
        payload = {"quantity": 15, "price": 3000}
        gtt.modify_gtt("GTT002", payload)
        call_kwargs = client.put.call_args[1]
        assert call_kwargs.get("json") == payload

    def test_modify_gtt_success_response(self):
        client = MagicMock()
        client.put.return_value = {"status": "success"}
        gtt = UpstoxGtt(client)
        resp = gtt.modify_gtt("GTT001", {"quantity": 5})
        assert resp.success is True
        assert resp.order_id == "GTT001"

    def test_modify_gtt_error_response(self):
        client = MagicMock()
        client.put.return_value = {"status": "error"}
        gtt = UpstoxGtt(client)
        resp = gtt.modify_gtt("GTT001", {"quantity": 5})
        assert resp.success is False


class TestCancelGtt:
    def test_cancel_gtt_calls_correct_endpoint(self):
        client = MagicMock()
        client.delete.return_value = {"status": "success"}
        gtt = UpstoxGtt(client)
        gtt.cancel_gtt("GTT999")
        call_args = client.delete.call_args
        endpoint = call_args[0][0]
        assert "gtt" in endpoint.lower()
        assert "GTT999" in endpoint


class TestIsSuccess:
    def test_is_success_with_success_status(self):
        gtt = UpstoxGtt(MagicMock())
        assert gtt._is_success({"status": "success"}) is True

    def test_is_success_with_ok_status(self):
        gtt = UpstoxGtt(MagicMock())
        assert gtt._is_success({"status": "ok"}) is True

    def test_is_success_with_ok_uppercase(self):
        gtt = UpstoxGtt(MagicMock())
        assert gtt._is_success({"status": "OK"}) is True

    def test_is_success_with_error_status(self):
        gtt = UpstoxGtt(MagicMock())
        assert gtt._is_success({"status": "error"}) is False

    def test_is_success_with_none_status(self):
        gtt = UpstoxGtt(MagicMock())
        assert gtt._is_success({"status": None}) is False

    def test_is_success_with_empty_dict(self):
        gtt = UpstoxGtt(MagicMock())
        assert gtt._is_success({}) is False

    def test_is_success_with_non_dict(self):
        gtt = UpstoxGtt(MagicMock())
        assert gtt._is_success("success") is False
        assert gtt._is_success(None) is False
        assert gtt._is_success(42) is False

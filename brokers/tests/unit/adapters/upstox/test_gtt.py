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

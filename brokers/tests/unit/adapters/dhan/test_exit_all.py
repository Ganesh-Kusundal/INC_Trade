import pytest
from unittest.mock import MagicMock, patch

from brokers.adapters.dhan.exit_all import DhanExitAll


class TestDhanExitAllInit:
    def setup_method(self):
        self.client = MagicMock()
        self.exit_all = DhanExitAll(self.client)

    def test_stores_client(self):
        assert self.exit_all._client is self.client


class TestCloseAllPositions:
    def setup_method(self):
        self.client = MagicMock()
        self.client.client_id = "CLIENT123"
        self.exit_all = DhanExitAll(self.client)

    def test_closes_long_position(self):
        self.client.get.return_value = [
            {"buyQty": 10, "sellQty": 0, "exchangeSegment": "NSE_EQ",
             "securityId": "SEC1", "productType": "INTRADAY"}
        ]
        self.client.post.return_value = {"status": "success"}

        result = self.exit_all.close_all_positions()

        assert result["squared_off"] == 1
        call_args = self.client.post.call_args
        assert call_args[0][0] is not None
        payload = call_args[1]["json"]
        assert payload["transactionType"] == 2
        assert payload["quantity"] == 10
        assert payload["dhanClientId"] == "CLIENT123"
        assert payload["orderType"] == 1

    def test_closes_short_position(self):
        self.client.get.return_value = [
            {"buyQty": 0, "sellQty": 5, "exchangeSegment": "NFO",
             "securityId": "SEC2", "productType": "INTRADAY"}
        ]
        self.client.post.return_value = {"status": "success"}

        result = self.exit_all.close_all_positions()

        assert result["squared_off"] == 1
        payload = self.client.post.call_args[1]["json"]
        assert payload["transactionType"] == 1
        assert payload["quantity"] == 5

    def test_skips_flat_position(self):
        self.client.get.return_value = [
            {"buyQty": 5, "sellQty": 5, "exchangeSegment": "NSE_EQ",
             "securityId": "SEC3", "productType": "INTRADAY"}
        ]

        result = self.exit_all.close_all_positions()

        assert result["squared_off"] == 0
        self.client.post.assert_not_called()

    def test_empty_positions(self):
        self.client.get.return_value = []

        result = self.exit_all.close_all_positions()

        assert result["squared_off"] == 0
        self.client.post.assert_not_called()

    def test_positions_from_dict_response(self):
        self.client.get.return_value = {"data": [
            {"buyQty": 3, "sellQty": 0, "exchangeSegment": "NSE_EQ",
             "securityId": "SEC4", "productType": "INTRADAY"}
        ]}
        self.client.post.return_value = {"status": "success"}

        result = self.exit_all.close_all_positions()

        assert result["squared_off"] == 1
        payload = self.client.post.call_args[1]["json"]
        assert payload["transactionType"] == 2
        assert payload["quantity"] == 3

    def test_handles_post_exception(self):
        self.client.get.return_value = [
            {"buyQty": 10, "sellQty": 0, "exchangeSegment": "NSE_EQ",
             "securityId": "SEC5", "productType": "INTRADAY"}
        ]
        self.client.post.side_effect = RuntimeError("connection lost")

        result = self.exit_all.close_all_positions()

        assert result["squared_off"] == 1
        assert result["results"][0]["status"] == "error"
        assert "connection lost" in result["results"][0]["error"]


class TestCancelAllOrders:
    def setup_method(self):
        self.client = MagicMock()
        self.exit_all = DhanExitAll(self.client)

    def test_cancels_active_orders(self):
        self.client.get.return_value = [
            {"orderId": "O1", "orderStatus": "OPEN"},
            {"orderId": "O2", "orderStatus": "PENDING"},
            {"orderId": "O3", "orderStatus": "COMPLETE"},
        ]
        self.client.post.return_value = {"status": "success"}

        result = self.exit_all.cancel_all_orders()

        assert result["cancelled"] == 2
        assert self.client.post.call_count == 2

    def test_cancels_transit_orders(self):
        self.client.get.return_value = [
            {"orderId": "O1", "orderStatus": "TRANSIT"},
            {"orderId": "O2", "orderStatus": "PARTIALLY_FILLED"},
        ]
        self.client.post.return_value = {"status": "success"}

        result = self.exit_all.cancel_all_orders()

        assert result["cancelled"] == 2

    def test_empty_orders(self):
        self.client.get.return_value = []

        result = self.exit_all.cancel_all_orders()

        assert result["cancelled"] == 0
        self.client.post.assert_not_called()

    def test_orders_from_dict_response(self):
        self.client.get.return_value = {"data": [
            {"orderId": "O1", "orderStatus": "OPEN"},
        ]}
        self.client.post.return_value = {"status": "success"}

        result = self.exit_all.cancel_all_orders()

        assert result["cancelled"] == 1

    def test_handles_cancel_exception(self):
        self.client.get.return_value = [
            {"orderId": "O1", "orderStatus": "OPEN"},
        ]
        self.client.post.side_effect = RuntimeError("timeout")

        result = self.exit_all.cancel_all_orders()

        assert result["cancelled"] == 1
        assert result["results"][0]["status"] == "error"
        assert "timeout" in result["results"][0]["error"]

    def test_skips_order_without_order_id(self):
        self.client.get.return_value = [
            {"orderStatus": "OPEN"},
        ]

        result = self.exit_all.cancel_all_orders()

        assert result["cancelled"] == 0
        self.client.post.assert_not_called()


class TestThreadPoolExecutor:
    def setup_method(self):
        self.client = MagicMock()
        self.client.client_id = "CLIENT123"
        self.exit_all = DhanExitAll(self.client)

    def test_max_workers_bounded(self):
        self.client.get.return_value = [
            {"buyQty": i, "sellQty": 0, "exchangeSegment": "NSE_EQ",
             "securityId": f"SEC{i}", "productType": "INTRADAY"}
            for i in range(1, 21)
        ]
        self.client.post.return_value = {"status": "success"}

        with patch("brokers.adapters.dhan.exit_all.ThreadPoolExecutor") as mock_tpe:
            mock_exec = MagicMock()
            mock_exec.__enter__ = MagicMock(return_value=mock_exec)
            mock_exec.__exit__ = MagicMock(return_value=False)
            mock_exec.submit.return_value = MagicMock(result=MagicMock(return_value={"ok": True}))
            mock_tpe.return_value = mock_exec

            with patch("brokers.adapters.dhan.exit_all.as_completed", return_value=[]):
                self.exit_all.close_all_positions()

            mock_tpe.assert_called_with(max_workers=10)

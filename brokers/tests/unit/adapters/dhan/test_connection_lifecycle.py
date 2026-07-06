from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from brokers.adapters.dhan.connection_lifecycle import ConnectionLifecycle


@pytest.fixture
def lifecycle():
    return ConnectionLifecycle(client_id="client_789")


class TestConnectionLifecycleInit:
    def test_initial_state(self, lifecycle):
        assert lifecycle._client_id == "client_789"
        assert lifecycle._depth_20_feed is None
        assert lifecycle._depth_200_feed is None
        assert lifecycle._depth_200_pool is None
        assert lifecycle._market_feed is None
        assert lifecycle._order_stream is None
        assert lifecycle._polling_feed is None

    def test_initial_state_with_token(self):
        lc = ConnectionLifecycle(
            client_id="c1",
            access_token="tok",
        )
        assert lc._access_token == "tok"
        assert lc._event_bus is None
        assert lc._lifecycle is None

    def test_initial_state_with_callable_token(self):
        fn = lambda: "tok"
        lc = ConnectionLifecycle(
            client_id="c1",
            access_token=fn,
        )
        assert lc._access_token is fn


class TestDepth20Feed:
    @patch("brokers_core.adapters.dhan.connection_lifecycle.DhanDepth20Stream")
    def test_create_depth_20_feed(self, MockStream, lifecycle):
        mock_feed = MagicMock()
        mock_feed.name = "depth20"
        MockStream.return_value = mock_feed
        result = lifecycle.create_depth_20_feed(access_token="tok")
        MockStream.assert_called_once_with(
            client_id="client_789",
            access_token="tok",
            instrument=None,
            event_bus=None,
        )
        assert result is mock_feed
        assert lifecycle.depth_20_feed is mock_feed

    @patch("brokers_core.adapters.dhan.connection_lifecycle.DhanDepth20Stream")
    def test_create_depth_20_feed_singleton(self, MockStream, lifecycle):
        mock_feed = MagicMock()
        mock_feed.name = "depth20"
        MockStream.return_value = mock_feed
        first = lifecycle.create_depth_20_feed(access_token="tok")
        second = lifecycle.create_depth_20_feed(access_token="other_tok")
        assert first is second
        MockStream.assert_called_once()

    @patch("brokers_core.adapters.dhan.connection_lifecycle.DhanDepth20Stream")
    def test_create_depth_20_feed_with_instruments(self, MockStream, lifecycle):
        mock_feed = MagicMock()
        mock_feed.name = "depth20"
        MockStream.return_value = mock_feed
        lifecycle.create_depth_20_feed(
            access_token="tok",
            instruments=[("NSE", "RELIANCE")],
        )
        call_kwargs = MockStream.call_args[1]
        assert call_kwargs["instrument"] == ("NSE", "RELIANCE")

    def test_depth_20_feed_property_none(self, lifecycle):
        assert lifecycle.depth_20_feed is None

    @patch("brokers_core.adapters.dhan.connection_lifecycle.DhanDepth20Stream")
    def test_depth_20_feed_property_setter(self, MockStream, lifecycle):
        mock_feed = MagicMock()
        lifecycle.depth_20_feed = mock_feed
        assert lifecycle.depth_20_feed is mock_feed

    @patch("brokers_core.adapters.dhan.connection_lifecycle.DhanDepth20Stream")
    def test_create_depth_20_feed_registers_with_lifecycle(self, MockStream):
        mock_lifecycle_mgr = MagicMock()
        lc = ConnectionLifecycle(
            client_id="c1",
            lifecycle=mock_lifecycle_mgr,
        )
        mock_feed = MagicMock()
        mock_feed.name = "depth20"
        MockStream.return_value = mock_feed
        lc.create_depth_20_feed(access_token="tok")
        mock_lifecycle_mgr.register.assert_called_once_with(mock_feed)


class TestDepth200Feed:
    @patch("brokers_core.adapters.dhan.connection_lifecycle.Depth200ConnectionPool")
    def test_create_depth_200_feed_creates_pool(self, MockPool, lifecycle):
        mock_pool = MagicMock()
        MockPool.return_value = mock_pool
        result = lifecycle.create_depth_200_feed(access_token="tok")
        MockPool.assert_called_once_with(
            client_id="client_789",
            access_token="tok",
            event_bus=None,
        )
        assert lifecycle.depth_200_pool is mock_pool

    @patch("brokers_core.adapters.dhan.connection_lifecycle.Depth200ConnectionPool")
    def test_create_depth_200_feed_reuses_pool(self, MockPool, lifecycle):
        mock_pool = MagicMock()
        MockPool.return_value = mock_pool
        lifecycle.create_depth_200_feed(access_token="tok")
        lifecycle.create_depth_200_feed(access_token="other")
        assert MockPool.call_count == 1

    def test_depth_200_pool_property_none(self, lifecycle):
        assert lifecycle.depth_200_pool is None

    def test_depth_200_feed_property_none(self, lifecycle):
        assert lifecycle.depth_200_feed is None

    def test_depth_200_feed_property_setter(self, lifecycle):
        lifecycle.depth_200_feed = "mock_feed"
        assert lifecycle.depth_200_feed == "mock_feed"


class TestRegisterWithLifecycle:
    def test_registers_when_lifecycle_present(self):
        mock_mgr = MagicMock()
        lc = ConnectionLifecycle(client_id="c1", lifecycle=mock_mgr)
        mock_svc = MagicMock()
        lc._register_with_lifecycle(mock_svc, "test_svc")
        mock_mgr.register.assert_called_once_with(mock_svc)

    def test_noop_when_no_lifecycle(self, lifecycle):
        lifecycle._register_with_lifecycle(MagicMock(), "test_svc")

    def test_handles_register_exception(self):
        mock_mgr = MagicMock()
        mock_mgr.register.side_effect = RuntimeError("fail")
        lc = ConnectionLifecycle(client_id="c1", lifecycle=mock_mgr)
        lc._register_with_lifecycle(MagicMock(), "test_svc")


class TestClose:
    def test_close_stops_depth20_feed(self, lifecycle):
        mock_feed = MagicMock()
        lifecycle._depth_20_feed = mock_feed
        lifecycle.close()
        mock_feed.stop.assert_called_once_with(timeout_seconds=5.0)

    def test_close_stops_depth200_feed(self, lifecycle):
        mock_feed = MagicMock()
        lifecycle._depth_200_feed = mock_feed
        lifecycle.close()
        mock_feed.stop.assert_called_once_with(timeout_seconds=5.0)

    def test_close_closes_depth200_pool(self):
        mock_pool = MagicMock()
        lc = ConnectionLifecycle(client_id="c1")
        lc._depth_200_pool = mock_pool
        lc.close()
        mock_pool.close_all.assert_called_once()

    def test_close_stops_all_services(self):
        lc = ConnectionLifecycle(client_id="c1")
        mock_feed = MagicMock()
        mock_order = MagicMock()
        mock_polling = MagicMock()
        mock_depth20 = MagicMock()
        mock_depth200 = MagicMock()
        lc._market_feed = mock_feed
        lc._order_stream = mock_order
        lc._polling_feed = mock_polling
        lc._depth_20_feed = mock_depth20
        lc._depth_200_feed = mock_depth200
        lc.close(timeout_seconds=10.0)
        for svc in [mock_feed, mock_order, mock_polling, mock_depth20, mock_depth200]:
            svc.stop.assert_called_once_with(timeout_seconds=10.0)

    def test_close_handles_stop_exception(self, lifecycle):
        mock_feed = MagicMock()
        mock_feed.stop.side_effect = RuntimeError("timeout")
        lifecycle._depth_20_feed = mock_feed
        lifecycle.close()

    def test_close_noop_when_no_services(self, lifecycle):
        lifecycle.close()

    def test_close_pool_exception_handled(self):
        mock_pool = MagicMock()
        mock_pool.close_all.side_effect = RuntimeError("pool error")
        lc = ConnectionLifecycle(client_id="c1")
        lc._depth_200_pool = mock_pool
        lc.close()

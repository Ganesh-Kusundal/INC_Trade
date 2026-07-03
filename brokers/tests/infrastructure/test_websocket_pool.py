"""Tests for WebSocket connection pool infrastructure."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from brokers.infrastructure.websocket_pool import (
    WebSocketConnection,
    WebSocketConnectionPool,
)


@pytest.fixture(scope="module", autouse=True)
def mock_ws_class():
    """Module-scoped global fixture to patch WebSocketApp.

    Ensures the mock remains active for any asynchronous background threads
    even after individual tests finish, preventing leaks to the real network.
    """
    with patch("websocket.WebSocketApp") as mock:
        mock_ws = MagicMock()
        mock_ws._closed = False

        def mock_close():
            mock_ws._closed = True

        mock_ws.close.side_effect = mock_close

        def default_run_forever(*args, **kwargs):
            mock_ws._closed = False
            # Call on_open to simulate successful connection
            if mock.call_args:
                _, call_kwargs = mock.call_args
                on_open_cb = call_kwargs.get("on_open")
                if on_open_cb:
                    on_open_cb(mock_ws)

            # Block until close() is called
            while not mock_ws._closed:
                time.sleep(0.001)

            # Trigger on_close callback if present
            if mock.call_args:
                _, call_kwargs = mock.call_args
                on_close_cb = call_kwargs.get("on_close")
                if on_close_cb:
                    on_close_cb(mock_ws, 1000, "Normal closure")

        mock_ws.run_forever.side_effect = default_run_forever
        mock.return_value = mock_ws
        yield mock


@pytest.fixture(autouse=True)
def speed_up_reconnect():
    """Patch default reconnect delay to keep tests extremely fast."""
    original_get_connection = WebSocketConnectionPool.get_connection

    def patched_get_connection(*args, **kwargs):
        kwargs.setdefault("reconnect_delay", 0.001)
        return original_get_connection(*args, **kwargs)

    with patch.object(
        WebSocketConnectionPool, "get_connection", patched_get_connection
    ):
        yield


@pytest.fixture(autouse=True)
def clean_pool():
    """Ensure WebSocket pool is cleaned up before and after every test."""
    WebSocketConnectionPool.cleanup()
    yield
    WebSocketConnectionPool.cleanup()


class TestWebSocketConnectionPool:
    """Test WebSocket connection pooling functionality."""

    def test_single_connection_reuse(self, mock_ws_class):
        """Test that same configuration reuses connection."""
        mock_ws_class.reset_mock()
        on_message = MagicMock()

        conn1 = WebSocketConnectionPool.get_connection(
            "wss://test.com/ws",
            {"token": "test123"},
            on_message,
        )
        conn1.start()
        time.sleep(0.05)

        conn2 = WebSocketConnectionPool.get_connection(
            "wss://test.com/ws",
            {"token": "test123"},
            on_message,
        )

        assert conn1 is conn2
        assert mock_ws_class.call_count == 1

        WebSocketConnectionPool.release_connection(conn1)
        WebSocketConnectionPool.release_connection(conn2)

    def test_different_connections_for_different_configs(self, mock_ws_class):
        """Test that different configurations create separate connections."""
        mock_ws_class.reset_mock()
        on_message_a = MagicMock()
        on_message_b = MagicMock()

        conn1 = WebSocketConnectionPool.get_connection(
            "wss://test.com/ws",
            {"token": "tokenA"},
            on_message_a,
        )
        conn1.start()
        time.sleep(0.05)

        conn2 = WebSocketConnectionPool.get_connection(
            "wss://test.com/ws",
            {"token": "tokenB"},
            on_message_b,
        )
        conn2.start()
        time.sleep(0.05)

        assert conn1 is not conn2
        assert mock_ws_class.call_count >= 2

        WebSocketConnectionPool.release_connection(conn1)
        WebSocketConnectionPool.release_connection(conn2)

    def test_reference_counting(self):
        """Test that connections are cleaned up when no longer referenced."""
        on_message = MagicMock()

        conn = WebSocketConnectionPool.get_connection(
            "wss://test.com/ws",
            {"token": "test123"},
            on_message,
        )

        assert conn.reference_count == 1

        conn2 = WebSocketConnectionPool.get_connection(
            "wss://test.com/ws",
            {"token": "test123"},
            on_message,
        )

        assert conn is conn2
        assert conn.reference_count == 2

        WebSocketConnectionPool.release_connection(conn)
        assert conn.reference_count == 1

        WebSocketConnectionPool.release_connection(conn2)
        assert conn.reference_count == 0

    def test_connection_state_management(self):
        """Test connection state transitions."""
        on_message = MagicMock()

        conn = WebSocketConnectionPool.get_connection(
            "wss://test.com/ws",
            {"token": "test123"},
            on_message,
        )

        # Initially connecting (auto-started by get_connection)
        assert conn.connection_state == "connecting"

        time.sleep(0.05)
        # Should transition to connected (via default_run_forever calling on_open)
        assert conn.connection_state == "connected"

        # Stop connection
        conn.stop()
        assert conn.connection_state == "disconnected"

        WebSocketConnectionPool.release_connection(conn)

    def test_subscription_management(self):
        """Test subscription tracking."""
        conn = WebSocketConnectionPool.get_connection(
            "wss://test.com/ws",
            {"token": "test123"},
            MagicMock(),
        )

        conn.subscribe("SYM1")
        conn.subscribe("SYM2")
        conn.subscribe("SYM1")  # Duplicate

        assert conn.subscription_count == 2

        conn.unsubscribe("SYM1")
        assert conn.subscription_count == 1

        WebSocketConnectionPool.release_connection(conn)

    def test_thread_safety(self):
        """Test thread-safe operations."""
        conn = WebSocketConnectionPool.get_connection(
            "wss://test.com/ws",
            {"token": "test123"},
            MagicMock(),
        )

        results = []

        def worker(worker_id):
            for i in range(10):
                conn.subscribe(f"SYM{worker_id}_{i}")
                time.sleep(0.001)
                conn.unsubscribe(f"SYM{worker_id}_{i}")
            results.append(worker_id)

        threads = []
        for i in range(3):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        assert len(results) == 3
        assert conn.subscription_count == 0

        WebSocketConnectionPool.release_connection(conn)

    def test_pool_stats(self):
        """Test pool statistics."""
        conn1 = WebSocketConnectionPool.get_connection(
            "wss://test1.com/ws",
            {"token": "token1"},
            MagicMock(),
        )

        conn2 = WebSocketConnectionPool.get_connection(
            "wss://test2.com/ws",
            {"token": "token2"},
            MagicMock(),
        )

        stats = WebSocketConnectionPool.get_pool_stats()
        assert stats["active_connections"] == 2
        assert len(stats["connection_details"]) == 2

        WebSocketConnectionPool.release_connection(conn1)
        WebSocketConnectionPool.release_connection(conn2)

    def test_cleanup(self):
        """Test pool cleanup."""
        conn = WebSocketConnectionPool.get_connection(
            "wss://test.com/ws",
            {"token": "test123"},
            MagicMock(),
        )

        initial_stats = WebSocketConnectionPool.get_pool_stats()
        assert initial_stats["active_connections"] == 1

        WebSocketConnectionPool.cleanup()

        stats = WebSocketConnectionPool.get_pool_stats()
        assert stats["active_connections"] == 0


class TestPooledStreamingIntegration:
    """Test integration with pooled streaming classes."""

    def test_market_data_streaming(self, mock_ws_class):
        """Test pooled market data streaming."""
        from brokers.adapters.dhan.streaming_pool import PooledDhanStreaming

        mock_ws_class.reset_mock()

        stream1 = PooledDhanStreaming(
            access_token="test_token", client_id="test_client"
        )
        stream2 = PooledDhanStreaming(
            access_token="test_token", client_id="test_client"
        )

        stream1.start()
        stream2.start()

        time.sleep(0.05)

        stream1.subscribe("RELIANCE", "NSE")
        stream2.subscribe("TCS", "NSE")

        assert stream1.is_connected
        assert stream2.is_connected

        stream1.stop()
        stream2.stop()

    def test_depth20_streaming(self):
        """Test pooled depth20 streaming."""
        from brokers.adapters.dhan.streaming_pool import PooledDhanDepth20Stream

        stream = PooledDhanDepth20Stream(
            access_token="test_token", client_id="test_client"
        )

        stream.start()
        time.sleep(0.05)
        assert stream.is_connected

        stream.subscribe("NIFTY", "NFO")
        stream.stop()

    def test_connection_reuse_across_instances(self, mock_ws_class):
        """Test that multiple gateway instances share connections."""
        from brokers.adapters.dhan.streaming_pool import PooledDhanStreaming

        mock_ws_class.reset_mock()

        gateway1_streaming = PooledDhanStreaming("token", "client")
        gateway2_streaming = PooledDhanStreaming("token", "client")
        gateway3_streaming = PooledDhanStreaming("token", "client")

        gateway1_streaming.start()
        gateway2_streaming.start()
        gateway3_streaming.start()

        time.sleep(0.05)

        assert mock_ws_class.call_count == 1
        assert gateway1_streaming.is_connected
        assert gateway2_streaming.is_connected
        assert gateway3_streaming.is_connected

        gateway1_streaming.stop()
        gateway2_streaming.stop()
        gateway3_streaming.stop()

        stats = WebSocketConnectionPool.get_pool_stats()
        # The connection may remain in pool for reuse but must have 0 references
        assert (
            stats["active_connections"] == 0
            or stats["connection_details"][0]["ref_count"] == 0
        )

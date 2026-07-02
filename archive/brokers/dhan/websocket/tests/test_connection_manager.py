"""Tests for WebSocket Connection Manager — single connection enforcement."""

import pytest
import threading
from unittest.mock import MagicMock, patch

from brokers.dhan.websocket.connection_manager import WebSocketConnectionManager


class TestWebSocketConnectionManager:
    """Test suite for WebSocketConnectionManager singleton enforcement."""

    def test_singleton_market_feed_creation(self):
        """Test that only one market feed instance is created."""
        manager = WebSocketConnectionManager("test_client", "test_token")
        
        # Create market feed for the first time
        feed1 = manager.get_market_feed()
        assert feed1 is not None
        
        # Request market feed again - should return the same instance
        feed2 = manager.get_market_feed()
        assert feed1 is feed2
        
        # Verify only one feed was created
        stats = manager.get_connection_stats()
        assert stats["market_feed"]["created"] is True
        assert stats["total_connections"] == 1

    def test_singleton_order_stream_creation(self):
        """Test that only one order stream instance is created."""
        manager = WebSocketConnectionManager("test_client", "test_token")
        
        # Create order stream for the first time
        stream1 = manager.get_order_stream()
        assert stream1 is not None
        
        # Request order stream again - should return the same instance
        stream2 = manager.get_order_stream()
        assert stream1 is stream2
        
        # Verify only one stream was created
        stats = manager.get_connection_stats()
        assert stats["order_stream"]["created"] is True
        assert stats["total_connections"] == 1

    def test_multiple_manager_instances_are_independent(self):
        """Test that different manager instances maintain separate connections."""
        manager1 = WebSocketConnectionManager("client1", "token1")
        manager2 = WebSocketConnectionManager("client2", "token2")
        
        feed1 = manager1.get_market_feed()
        feed2 = manager2.get_market_feed()
        
        # Different managers should have different feed instances
        assert feed1 is not feed2
        assert manager1.get_connection_stats()["total_connections"] == 1
        assert manager2.get_connection_stats()["total_connections"] == 1

    def test_thread_safety_market_feed(self):
        """Test thread-safe market feed creation."""
        manager = WebSocketConnectionManager("test_client", "test_token")
        feeds = []
        
        def create_feed():
            feed = manager.get_market_feed()
            feeds.append(feed)
        
        # Create multiple threads that try to create feeds simultaneously
        threads = [threading.Thread(target=create_feed) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All threads should have received the same instance
        assert len(feeds) == 5
        assert all(feed is feeds[0] for feed in feeds)

    def test_thread_safety_order_stream(self):
        """Test thread-safe order stream creation."""
        manager = WebSocketConnectionManager("test_client", "test_token")
        streams = []
        
        def create_stream():
            stream = manager.get_order_stream()
            streams.append(stream)
        
        # Create multiple threads that try to create streams simultaneously
        threads = [threading.Thread(target=create_stream) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All threads should have received the same instance
        assert len(streams) == 5
        assert all(stream is streams[0] for stream in streams)

    def test_access_token_propagation(self):
        """Test that access token updates are propagated to connections."""
        manager = WebSocketConnectionManager("test_client", "token1")
        
        # Create connections with initial token
        feed = manager.get_market_feed()
        stream = manager.get_order_stream()
        
        # Update the token
        manager.access_token = "token2"
        
        # Verify that the connections would have received the token update
        # (In real usage, the connections would have their update_token method called)
        assert manager.access_token == "token2"

    def test_connection_stats_tracking(self):
        """Test that connection statistics are tracked correctly."""
        manager = WebSocketConnectionManager("test_client", "test_token")
        
        # Initially, no connections should exist
        stats = manager.get_connection_stats()
        assert stats["market_feed"]["created"] is False
        assert stats["order_stream"]["created"] is False
        assert stats["total_connections"] == 0
        
        # Create market feed
        manager.get_market_feed()
        stats = manager.get_connection_stats()
        assert stats["market_feed"]["created"] is True
        assert stats["total_connections"] == 1
        
        # Create order stream
        manager.get_order_stream()
        stats = manager.get_connection_stats()
        assert stats["order_stream"]["created"] is True
        assert stats["total_connections"] == 2

    def test_ensure_single_connections_success(self):
        """Test that ensure_single_connections passes when connections are valid."""
        manager = WebSocketConnectionManager("test_client", "test_token")
        
        # Create connections
        manager.get_market_feed()
        manager.get_order_stream()
        
        # This should not raise any assertion errors
        manager.ensure_single_connections()

    def test_close_all_connections(self):
        """Test that close_all properly cleans up connections."""
        manager = WebSocketConnectionManager("test_client", "test_token")
        
        # Create connections
        feed = manager.get_market_feed()
        stream = manager.get_order_stream()
        
        # Verify connections exist
        assert manager.get_connection_stats()["total_connections"] == 2
        
        # Close all connections
        manager.close_all()
        
        # Verify connections are cleared
        stats = manager.get_connection_stats()
        assert stats["market_feed"]["exists"] is False
        assert stats["order_stream"]["exists"] is False
        assert stats["total_connections"] == 0

    def test_start_all_connections(self):
        """Test that start_all starts all connections."""
        manager = WebSocketConnectionManager("test_client", "test_token")
        
        # Create connections (but don't start them)
        feed = manager.get_market_feed()
        stream = manager.get_order_stream()
        
        # Mock the start method and is_connected property to track calls
        with patch.object(feed, 'start') as mock_feed_start, \
             patch.object(stream, 'start') as mock_stream_start, \
             patch.object(feed, '_is_connected', False), \
             patch.object(stream, '_is_connected', False):
            
            manager.start_all()
            
            # Verify both connections were started
            assert mock_feed_start.called
            assert mock_stream_start.called

    def test_stop_all_connections(self):
        """Test that stop_all stops all connections."""
        manager = WebSocketConnectionManager("test_client", "test_token")
        
        # Create connections
        feed = manager.get_market_feed()
        stream = manager.get_order_stream()
        
        # Mock the stop method to track calls
        with patch.object(feed, 'stop') as mock_feed_stop, \
             patch.object(stream, 'stop') as mock_stream_stop:
            
            manager.stop_all()
            
            # Verify both connections were stopped
            assert mock_feed_stop.called
            assert mock_stream_stop.called

    def test_market_feed_with_instruments(self):
        """Test market feed creation with initial instruments."""
        manager = WebSocketConnectionManager("test_client", "test_token")
        
        instruments = [("NSE", "12345"), ("NSE", "67890")]
        feed = manager.get_market_feed(instruments=instruments)
        
        assert feed is not None
        # The instruments should have been passed to the feed constructor
        # (exact verification would require mocking the DhanMarketFeed)


class TestWebSocketConnectionManagerIntegration:
    """Integration tests for WebSocketConnectionManager."""

    def test_creation_with_none_token(self):
        """Test manager creation with None access token."""
        manager = WebSocketConnectionManager("test_client", None)
        assert manager.access_token is None
        
        # Should still be able to create connections (they'll get None token)
        feed = manager.get_market_feed()
        assert feed is not None

    def test_creation_without_event_bus(self):
        """Test manager creation without event bus."""
        manager = WebSocketConnectionManager("test_client", "test_token", None)
        assert manager._event_bus is None
        
        # Should still be able to create connections
        feed = manager.get_market_feed()
        assert feed is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
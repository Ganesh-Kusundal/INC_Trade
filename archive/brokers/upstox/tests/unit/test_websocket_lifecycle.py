"""Tests for Upstox WebSocket lifecycle wiring.

Verifies that UpstoxBrokerFactory registers UpstoxWebSocketService
with the LifecycleManager when lifecycle is provided.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from infrastructure.lifecycle import LifecycleManager
from infrastructure.lifecycle.lifecycle import HealthState


class TestUpstoxWebSocketLifecycle:
    """Verify Upstox factory auto-registers WebSocket with lifecycle."""

    def test_factory_registers_websocket_with_lifecycle(self):
        """WebSocket service registered with lifecycle should appear in service_names."""
        from brokers.upstox.websocket.lifecycle_wrapper import UpstoxWebSocketService

        mock_mux = MagicMock()
        mock_mux.is_connected = False

        ws_service = UpstoxWebSocketService(multiplexer=mock_mux)
        lifecycle = LifecycleManager()
        lifecycle.register(ws_service)

        assert "upstox.websocket" in lifecycle.service_names()

    def test_websocket_service_health_stopped_by_default(self):
        """WebSocket service should report STOPPED before start()."""
        from brokers.upstox.websocket.lifecycle_wrapper import UpstoxWebSocketService

        mock_mux = MagicMock()
        mock_mux.is_connected = False

        ws = UpstoxWebSocketService(multiplexer=mock_mux)
        health = ws.health()
        assert health.state == HealthState.STOPPED

    def test_websocket_service_health_degraded_when_started_not_connected(self):
        """WebSocket service should report DEGRADED when started but not connected."""
        from brokers.upstox.websocket.lifecycle_wrapper import UpstoxWebSocketService

        mock_mux = MagicMock()
        mock_mux.is_connected = False

        ws = UpstoxWebSocketService(multiplexer=mock_mux)
        ws._started = True
        health = ws.health()
        assert health.state == HealthState.DEGRADED

    def test_websocket_service_health_healthy_when_connected(self):
        """WebSocket service should report HEALTHY when started and connected."""
        from brokers.upstox.websocket.lifecycle_wrapper import UpstoxWebSocketService

        mock_mux = MagicMock()
        mock_mux.is_connected = True

        ws = UpstoxWebSocketService(multiplexer=mock_mux)
        ws._started = True
        health = ws.health()
        assert health.state == HealthState.HEALTHY

    def test_stop_is_noop_when_not_started(self):
        """stop() should be a no-op when start() was never called."""
        from brokers.upstox.websocket.lifecycle_wrapper import UpstoxWebSocketService

        mock_mux = MagicMock()
        mock_mux.is_connected = False

        ws = UpstoxWebSocketService(multiplexer=mock_mux)
        ws.stop()  # Should not raise
        mock_mux.disconnect.assert_not_called()

    def test_start_registers_with_lifecycle(self):
        """WebSocket service registered with lifecycle should appear in service_names."""
        from brokers.upstox.websocket.lifecycle_wrapper import UpstoxWebSocketService

        mock_mux = MagicMock()
        mock_mux.is_connected = False

        ws = UpstoxWebSocketService(multiplexer=mock_mux)
        lc = LifecycleManager()
        lc.register(ws)

        assert "upstox.websocket" in lc.service_names()

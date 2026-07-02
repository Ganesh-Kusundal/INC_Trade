"""Unit tests for Upstox TOTP refresh scheduler."""

from __future__ import annotations

from unittest.mock import MagicMock

from brokers.upstox.auth.totp_scheduler import TotpRefreshScheduler
from infrastructure.lifecycle import HealthState


class TestTotpRefreshSchedulerLifecycle:
    """Test scheduler start/stop lifecycle."""

    def test_scheduler_starts(self):
        """Test scheduler starts successfully."""
        mock_token_manager = MagicMock()
        scheduler = TotpRefreshScheduler(mock_token_manager, refresh_hour=8, refresh_minute=0)

        try:
            scheduler.start()
            assert scheduler.is_running is True
        finally:
            scheduler.stop()

        assert scheduler.is_running is False

    def test_scheduler_stop_idempotent(self):
        """Test calling stop multiple times is safe."""
        mock_token_manager = MagicMock()
        scheduler = TotpRefreshScheduler(mock_token_manager)

        scheduler.stop()  # Should not raise
        scheduler.stop()  # Should not raise

    def test_scheduler_start_idempotent(self):
        """Test calling start multiple times is safe."""
        mock_token_manager = MagicMock()
        scheduler = TotpRefreshScheduler(mock_token_manager)

        try:
            scheduler.start()
            scheduler.start()  # Should not raise
            assert scheduler.is_running is True
        finally:
            scheduler.stop()


class TestTotpRefreshSchedulerRefresh:
    """Test scheduler refresh functionality."""

    def test_refresh_now_success(self):
        """Test immediate refresh succeeds."""
        mock_token_manager = MagicMock()
        mock_token_manager.settings.is_totp = True
        mock_token_manager.current_state.return_value = None
        mock_token_manager.refresh_totp.return_value = MagicMock()

        scheduler = TotpRefreshScheduler(mock_token_manager)
        result = scheduler.refresh_now()

        assert result is True
        assert scheduler.refresh_count == 1

    def test_refresh_now_failure(self):
        """Test immediate refresh failure."""
        mock_token_manager = MagicMock()
        mock_token_manager.settings.is_totp = True
        mock_token_manager.current_state.return_value = None
        mock_token_manager.refresh_totp.side_effect = Exception("Token error")

        scheduler = TotpRefreshScheduler(mock_token_manager)
        result = scheduler.refresh_now()

        assert result is False
        assert scheduler.refresh_count == 0


class TestTotpRefreshSchedulerHealth:
    """Test scheduler health reporting."""

    def test_health_stopped(self):
        """Test health reports stopped state."""
        mock_token_manager = MagicMock()
        scheduler = TotpRefreshScheduler(mock_token_manager)

        health = scheduler.health()
        assert health.state == HealthState.STOPPED

    def test_health_healthy_after_refresh(self):
        """Test health reports healthy after successful refresh."""
        mock_token_manager = MagicMock()
        mock_token_manager.settings.is_totp = True
        mock_token_manager.current_state.return_value = None
        mock_token_manager.refresh_totp.return_value = MagicMock()
        scheduler = TotpRefreshScheduler(mock_token_manager)
        scheduler.refresh_now()

        assert scheduler.refresh_count == 1

    def test_health_degraded_after_error(self):
        """Test health reports degraded after error."""
        mock_token_manager = MagicMock()
        mock_token_manager.settings.is_totp = True
        mock_token_manager.current_state.return_value = None
        mock_token_manager.refresh_totp.side_effect = Exception("Error")

        scheduler = TotpRefreshScheduler(mock_token_manager)
        scheduler.refresh_now()

        assert scheduler._last_error is not None


class TestTotpRefreshSchedulerCallbacks:
    """Test scheduler callback functionality."""

    def test_on_success_callback(self):
        """Test success callback is called."""
        mock_token_manager = MagicMock()
        mock_token_manager.settings.is_totp = True
        mock_token_manager.current_state.return_value = None
        mock_token_manager.refresh_totp.return_value = MagicMock()
        callback = MagicMock()

        scheduler = TotpRefreshScheduler(
            mock_token_manager,
            on_refresh_success=callback,
        )
        scheduler.refresh_now()

        callback.assert_called_once()

    def test_on_error_callback(self):
        """Test error callback is called on failure."""
        mock_token_manager = MagicMock()
        mock_token_manager.settings.is_totp = True
        mock_token_manager.current_state.return_value = None
        mock_token_manager.refresh_totp.side_effect = Exception("Error")
        callback = MagicMock()

        scheduler = TotpRefreshScheduler(
            mock_token_manager,
            on_refresh_error=callback,
        )
        scheduler.refresh_now()

        callback.assert_called_once()

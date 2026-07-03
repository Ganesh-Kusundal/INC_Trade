from unittest.mock import MagicMock, patch

from brokers.adapters.dhan.gateway import DhanGateway
from brokers.adapters.dhan.metrics import with_metrics, with_rate_limit


def test_metrics_decorator():
    """Assert that cross-cutting concerns like metrics correctly wrap adapter logic."""
    mock_metric_tracker = MagicMock()

    @with_metrics("test_operation", mock_metric_tracker)
    def dummy_adapter_method(x, y):
        return x + y

    result = dummy_adapter_method(2, 3)
    assert result == 5
    # Depending on the actual implementation of with_metrics, we would assert the tracker was called
    # For now, this is a placeholder structure
    mock_metric_tracker.assert_called_once_with("test_operation", status="success")


def test_rate_limit_decorator():
    """Assert rate limit properly restricts or delays execution."""
    mock_rate_limiter = MagicMock()

    @with_rate_limit(mock_rate_limiter)
    def dummy_method():
        return "success"

    res = dummy_method()
    assert res == "success"
    mock_rate_limiter.acquire.assert_called_once()


def test_token_hot_swapping():
    """Verify that DhanGateway safely hot-swaps tokens across streaming and HTTP clients."""
    with patch(
        "brokers.adapters.dhan.auth.DhanAuth.generate_token",
        return_value="new_token_456",
    ):
        gw = DhanGateway(access_token="old_token_123", client_id="client_123", auto_refresh=False)

        # Manually trigger a token refresh via the connection manager
        new_token = gw._conn_mgr.refresh_token_for_http()
        assert new_token == "new_token_456"

        # After refresh, simulate the callback triggering the broadcast
        gw._conn_mgr._on_token_refreshed(new_token)

        # The broadcast should propagate the token to the streams
        # Check if stream access tokens were conceptually updated (via broadcast)
        assert gw.streaming._get_access_token() == "new_token_456"

        gw.close()

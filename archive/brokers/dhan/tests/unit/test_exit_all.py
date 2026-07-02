"""Unit tests for ExitAllAdapter."""

from brokers.dhan.exit_all import ExitAllAdapter


def test_exit_all_success(fake_client):
    """Verify POST /exitall response parsing."""
    fake_client.set_response(
        "POST",
        "/exitall",
        {
            "data": {
                "positionsClosed": 5,
                "ordersCancelled": 3,
                "success": True,
                "message": "All positions closed and orders cancelled",
            }
        },
    )
    adapter = ExitAllAdapter(fake_client)
    result = adapter.exit_all()

    assert result.success is True
    assert result.positions_closed == 5
    assert result.orders_cancelled == 3
    assert "All positions closed" in result.message


def test_exit_all_positions_closed(fake_client):
    """Verify positions_closed count."""
    fake_client.set_response(
        "POST",
        "/exitall",
        {
            "data": {
                "positionsClosed": 10,
                "ordersCancelled": 0,
                "success": True,
                "message": "10 positions closed",
            }
        },
    )
    adapter = ExitAllAdapter(fake_client)
    result = adapter.exit_all()

    assert result.positions_closed == 10


def test_exit_all_orders_cancelled(fake_client):
    """Verify orders_cancelled count."""
    fake_client.set_response(
        "POST",
        "/exitall",
        {
            "data": {
                "positionsClosed": 0,
                "ordersCancelled": 7,
                "success": True,
                "message": "7 orders cancelled",
            }
        },
    )
    adapter = ExitAllAdapter(fake_client)
    result = adapter.exit_all()

    assert result.orders_cancelled == 7

from domain import OrderStatus

from brokers.dhan.status_mapper import DHAN_STATUS_MAP


def test_partially_cancelled_maps_to_partially_cancelled():
    """PARTIALLY_CANCELLED is a distinct terminal state, not CANCELLED."""
    assert DHAN_STATUS_MAP["PARTIALLY_CANCELLED"] == OrderStatus.PARTIALLY_CANCELLED
    assert OrderStatus.PARTIALLY_CANCELLED.is_terminal

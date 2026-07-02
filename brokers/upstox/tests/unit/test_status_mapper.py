from domain import OrderStatus

from brokers.upstox.status_mapper import UPSTOX_STATUS_MAP


def test_cancel_pending_stays_non_terminal():
    assert UPSTOX_STATUS_MAP["CANCEL_PENDING"] == OrderStatus.OPEN

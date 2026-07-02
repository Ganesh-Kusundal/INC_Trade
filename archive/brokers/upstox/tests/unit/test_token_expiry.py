from __future__ import annotations

from datetime import datetime

from brokers.upstox.auth.token_expiry import IST, UpstoxTokenExpiry


def test_next_expiry_pre_market_is_today_at_330am_ist():
    now = datetime(2026, 5, 1, 1, 0, tzinfo=IST)
    expiry = UpstoxTokenExpiry.next_expiry_epoch_ms(now)
    expected = datetime(2026, 5, 1, 3, 30, tzinfo=IST)
    assert expiry == int(expected.timestamp() * 1000)


def test_next_expiry_post_330am_is_tomorrow_at_330am():
    now = datetime(2026, 5, 1, 10, 0, tzinfo=IST)
    expiry = UpstoxTokenExpiry.next_expiry_epoch_ms(now)
    expected = datetime(2026, 5, 2, 3, 30, tzinfo=IST)
    assert expiry == int(expected.timestamp() * 1000)


def test_next_expiry_exactly_at_330am_rolls_to_tomorrow():
    now = datetime(2026, 5, 1, 3, 30, tzinfo=IST)
    expiry = UpstoxTokenExpiry.next_expiry_epoch_ms(now)
    expected = datetime(2026, 5, 2, 3, 30, tzinfo=IST)
    assert expiry == int(expected.timestamp() * 1000)


def test_next_expiry_naive_datetime_is_treated_as_ist():
    now = datetime(2026, 5, 1, 1, 0)
    expiry = UpstoxTokenExpiry.next_expiry_epoch_ms(now)
    expected = datetime(2026, 5, 1, 3, 30, tzinfo=IST)
    assert expiry == int(expected.timestamp() * 1000)

"""Unit tests for Instrument expiry utility methods."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from inc_trade.market.instrument import Instrument


class TestInstrumentExpiry:
    def test_is_expired_no_expiry(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        assert inst.is_expired() is False

    def test_is_expired_in_past(self) -> None:
        past = datetime.now(UTC) - timedelta(days=1)
        inst = Instrument(symbol="X", exchange="NFO", expiry=past)
        assert inst.is_expired() is True

    def test_is_expired_in_future(self) -> None:
        future = datetime.now(UTC) + timedelta(days=30)
        inst = Instrument(symbol="X", exchange="NFO", expiry=future)
        assert inst.is_expired() is False

    def test_days_to_expiry_no_expiry(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        assert inst.days_to_expiry() is None

    def test_days_to_expiry_future(self) -> None:
        future = datetime.now(UTC) + timedelta(days=10)
        inst = Instrument(symbol="X", exchange="NFO", expiry=future)
        days = inst.days_to_expiry()
        assert days is not None
        # Allow 1-day tolerance for timezone edge cases
        assert 9 <= days <= 10

    def test_days_to_expiry_past(self) -> None:
        past = datetime.now(UTC) - timedelta(days=5)
        inst = Instrument(symbol="X", exchange="NFO", expiry=past)
        days = inst.days_to_expiry()
        assert days is not None
        assert days < 0

    def test_is_expiring_soon_no_expiry(self) -> None:
        inst = Instrument(symbol="RELIANCE", exchange="NSE")
        assert inst.is_expiring_soon() is False

    def test_is_expiring_soon_within_threshold(self) -> None:
        future = datetime.now(UTC) + timedelta(days=3)
        inst = Instrument(symbol="X", exchange="NFO", expiry=future)
        assert inst.is_expiring_soon(threshold_days=7) is True

    def test_is_expiring_soon_outside_threshold(self) -> None:
        future = datetime.now(UTC) + timedelta(days=30)
        inst = Instrument(symbol="X", exchange="NFO", expiry=future)
        assert inst.is_expiring_soon(threshold_days=7) is False

    def test_is_expiring_soon_already_expired(self) -> None:
        past = datetime.now(UTC) - timedelta(days=1)
        inst = Instrument(symbol="X", exchange="NFO", expiry=past)
        # Already expired, not "expiring soon"
        assert inst.is_expiring_soon() is False

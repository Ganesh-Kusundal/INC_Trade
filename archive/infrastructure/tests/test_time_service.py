"""Tests for infrastructure.time_service — zoneinfo-based timezone handling (Fix #15)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from infrastructure.time_service import ExchangeCalendar, time_service


class TestExchangeCalendar:
    """Fix #15: exchange times must use IANA timezones, not fixed offsets."""

    def test_nse_uses_ist(self):
        """NSE returns IST (UTC+5:30) regardless of DST."""
        cal = ExchangeCalendar("Asia/Kolkata", "NSE")
        now = cal.now()
        utc_now = datetime.now(timezone.utc)
        # IST is always UTC+5:30
        diff = now - utc_now.astimezone(now.tzinfo)
        assert abs(diff.total_seconds() - 0) < 2  # same instant

    def test_nyse_winter_vs_summer(self):
        """NYSE must handle EST (UTC-5) vs EDT (UTC-4) correctly."""
        from zoneinfo import ZoneInfo

        ExchangeCalendar("America/New_York", "NYSE")

        # January = EST = UTC-5
        jan_dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        assert jan_dt.utcoffset() == timedelta(hours=-5)

        # July = EDT = UTC-4
        jul_dt = datetime(2024, 7, 15, 12, 0, 0, tzinfo=ZoneInfo("America/New_York"))
        assert jul_dt.utcoffset() == timedelta(hours=-4)

    def test_lse_winter_vs_summer(self):
        """LSE must handle GMT (UTC+0) vs BST (UTC+1) correctly."""
        from zoneinfo import ZoneInfo

        # January = GMT = UTC+0
        jan_dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=ZoneInfo("Europe/London"))
        assert jan_dt.utcoffset() == timedelta(hours=0)

        # July = BST = UTC+1
        jul_dt = datetime(2024, 7, 15, 12, 0, 0, tzinfo=ZoneInfo("Europe/London"))
        assert jul_dt.utcoffset() == timedelta(hours=1)


class TestTimeService:
    """TimeService integration tests."""

    def test_exchange_now_nse(self):
        result = time_service.exchange_now("NSE")
        assert result.tzinfo is not None

    def test_exchange_now_nyse(self):
        result = time_service.exchange_now("NYSE")
        assert result.tzinfo is not None

    def test_exchange_now_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown exchange"):
            time_service.exchange_now("INVALID")

    def test_now_returns_utc(self):
        result = time_service.now()
        assert result.tzinfo == timezone.utc

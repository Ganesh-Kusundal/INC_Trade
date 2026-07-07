"""Centralized time service — single source of truth for time operations.

Handles UTC time, exchange-local time, and timestamp formatting.

Usage::

    from brokers.infrastructure.time_service import time_service

    now = time_service.now()
    exchange_time = time_service.exchange_now("NSE")
    formatted = time_service.format_timestamp(now)
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


class ExchangeCalendar:
    """Exchange-specific time handling."""

    def __init__(self, tz_name: str, name: str) -> None:
        self.tz = ZoneInfo(tz_name)
        self.name = name

    def now(self) -> datetime:
        return datetime.now(self.tz)


EXCHANGE_CALENDARS: dict[str, ExchangeCalendar] = {
    "NSE": ExchangeCalendar("Asia/Kolkata", "NSE"),
    "BSE": ExchangeCalendar("Asia/Kolkata", "BSE"),
    "MCX": ExchangeCalendar("Asia/Kolkata", "MCX"),
    "NYSE": ExchangeCalendar("America/New_York", "NYSE"),
    "NASDAQ": ExchangeCalendar("America/New_York", "NASDAQ"),
    "LSE": ExchangeCalendar("Europe/London", "LSE"),
}


class TimeService:
    """Centralized time service.

    Provides UTC time, exchange-local time, and formatting helpers.
    Testable: override ``_now_fn`` to inject deterministic time.
    """

    def __init__(self, *, now_fn: Callable[[], datetime] | None = None) -> None:
        self._now_fn = now_fn

    def now(self) -> datetime:
        """Current UTC time."""
        if self._now_fn is not None:
            return self._now_fn()
        return datetime.now(timezone.utc)

    def timestamp(self) -> float:
        """Unix timestamp (seconds since epoch)."""
        return time.time()

    def exchange_now(self, exchange: str) -> datetime:
        """Current time in the exchange's local timezone."""
        calendar = EXCHANGE_CALENDARS.get(exchange)
        if not calendar:
            raise ValueError(f"Unknown exchange: {exchange}")
        return calendar.now()

    def format_timestamp(
        self, dt: datetime | None = None, fmt: str = "%Y-%m-%dT%H:%M:%S.%fZ"
    ) -> str:
        """Format a datetime to string. Defaults to UTC now."""
        if dt is None:
            dt = self.now()
        return dt.strftime(fmt)

    def parse_iso(self, iso_str: str) -> datetime:
        """Parse an ISO 8601 datetime string."""
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))

    def epoch_now(self) -> int:
        """Current epoch time in seconds."""
        return int(time.time())

    def epoch_ms(self) -> int:
        """Current epoch time in milliseconds."""
        return int(time.time() * 1000)


# Module-level singleton
time_service = TimeService()


__all__ = ["EXCHANGE_CALENDARS", "ExchangeCalendar", "TimeService", "time_service"]

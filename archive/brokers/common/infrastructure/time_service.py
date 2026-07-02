"""Centralized time service for TradeXV2.

Provides a single source of truth for all time-related operations.
Handles timezone conversion, exchange calendars, and timestamp formatting.

Usage:
    from infrastructure.time_service import time_service

    now = time_service.now()
    exchange_time = time_service.exchange_now("NSE")
    formatted = time_service.format_timestamp(now)
"""

from __future__ import annotations

import time
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
    """Centralized time service."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def timestamp(self) -> float:
        return time.time()

    def exchange_now(self, exchange: str) -> datetime:
        calendar = EXCHANGE_CALENDARS.get(exchange)
        if not calendar:
            raise ValueError(f"Unknown exchange: {exchange}")
        return calendar.now()

    def format_timestamp(self, dt: datetime | None = None, fmt: str = "%Y-%m-%dT%H:%M:%S.%fZ") -> str:
        if dt is None:
            dt = self.now()
        return dt.strftime(fmt)

    def parse_iso(self, iso_str: str) -> datetime:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))

    def epoch_now(self) -> int:
        return int(time.time())

    def epoch_ms(self) -> int:
        return int(time.time() * 1000)


time_service = TimeService()

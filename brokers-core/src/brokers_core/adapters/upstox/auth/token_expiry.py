"""Daily 3:30 AM IST expiry fallback.

Upstox access tokens expire daily at 3:30 AM IST regardless of issue time.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
EXPIRY_TIME = time(3, 30)


class UpstoxTokenExpiry:
    @staticmethod
    def next_expiry_epoch_ms(now: datetime | None = None) -> int:
        if now is None:
            now = datetime.now(IST)
        elif now.tzinfo is None:
            now = now.replace(tzinfo=IST)
        else:
            now = now.astimezone(IST)

        expiry_today = datetime.combine(now.date(), EXPIRY_TIME, tzinfo=IST)
        if now >= expiry_today:
            expiry_today = expiry_today + timedelta(days=1)
        return int(expiry_today.timestamp() * 1000)

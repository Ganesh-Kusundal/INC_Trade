"""Market hours helpers for integration test skip guards."""

from __future__ import annotations

from datetime import datetime, time, timezone

import pytest

_IST = timezone(offset=__import__("datetime").timedelta(hours=5, minutes=30))
_MARKET_OPEN = time(9, 15)
_MARKET_CLOSE = time(15, 30)


def is_market_open() -> bool:
    """Return True if current IST time is within NSE trading hours (Mon-Fri)."""
    now = datetime.now(_IST)
    if now.weekday() >= 5:
        return False
    return _MARKET_OPEN <= now.time() <= _MARKET_CLOSE


skip_off_market = pytest.mark.skipif(
    not is_market_open(),
    reason="Market is closed — skipping live test",
)


def require_market_hours():
    """Decorator factory that skips a test if the market is closed."""
    return pytest.mark.skipif(
        not is_market_open(),
        reason="Requires open market hours",
    )

"""Clock port — injectable time source for testability.

Production uses real wall-clock time; tests inject a fake clock
to control time deterministically.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol


class ClockPort(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)

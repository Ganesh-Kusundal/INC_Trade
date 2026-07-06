"""Kill switch — emergency order blocking mechanism.

When engaged, ALL order placement is blocked regardless of
account, broker, or instrument. Modify/cancel still allowed.

Thread-safe: can be engaged from any thread.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class KillSwitch:
    """Emergency order blocking mechanism.

    When engaged, all order placement is blocked. Modify/cancel
    operations are still allowed to enable position management
    during emergencies.
    """

    def __init__(self) -> None:
        self._engaged = False
        self._lock = threading.Lock()
        self._reason = ""

    @property
    def is_engaged(self) -> bool:
        with self._lock:
            return self._engaged

    def engage(self, reason: str = "") -> None:
        """Engage the kill switch, blocking all new orders."""
        with self._lock:
            self._engaged = True
            self._reason = reason
            logger.critical("KILL SWITCH ENGAGED: %s", reason)

    def disengage(self) -> None:
        """Disengage the kill switch, allowing orders again."""
        with self._lock:
            self._engaged = False
            self._reason = ""
            logger.info("Kill switch disengaged")

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason

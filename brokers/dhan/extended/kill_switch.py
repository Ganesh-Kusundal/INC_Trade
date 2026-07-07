"""Dhan kill switch — emergency order cancellation.

API: POST /kill_switch — activate/deactivate
     GET /kill_switch — check status
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class KillSwitchResult:
    """Result of a kill switch operation."""

    active: bool = False
    message: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> KillSwitchResult:
        return cls(
            active=bool(data.get("active", False)),
            message=str(data.get("message", "")),
        )


class DhanKillSwitch:
    """Kill switch for emergency order cancellation.

    Usage::

        ks = DhanKillSwitch(client=dhan_client)
        result = ks.activate()
        status = ks.status()
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def activate(self) -> KillSwitchResult:
        """Activate the kill switch — cancels all open orders."""
        logger.info("dhan_kill_switch_activate")
        data = self._client.post("/kill_switch", json={"action": "ACTIVATE"})
        raw = data.get("data", data) if isinstance(data, dict) else {}
        return KillSwitchResult.from_dict(raw if isinstance(raw, dict) else {})

    def deactivate(self) -> KillSwitchResult:
        """Deactivate the kill switch."""
        logger.info("dhan_kill_switch_deactivate")
        data = self._client.post("/kill_switch", json={"action": "DEACTIVATE"})
        raw = data.get("data", data) if isinstance(data, dict) else {}
        return KillSwitchResult.from_dict(raw if isinstance(raw, dict) else {})

    def status(self) -> KillSwitchResult:
        """Check kill switch status."""
        data = self._client.get("/kill_switch")
        raw = data.get("data", data) if isinstance(data, dict) else {}
        return KillSwitchResult.from_dict(raw if isinstance(raw, dict) else {})


__all__ = ["DhanKillSwitch", "KillSwitchResult"]

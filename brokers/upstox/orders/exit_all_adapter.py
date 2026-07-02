"""Upstox exit-all adapter — close all positions and cancel all orders via kill switch."""

from __future__ import annotations

import logging
from typing import Any

from brokers.common.resilience.errors import ExitAllError
from brokers.upstox.kill_switch.client import UpstoxKillSwitchClient

logger = logging.getLogger(__name__)


class UpstoxExitAllAdapter:
    """Close all positions and cancel all open orders.

    Delegates to the Upstox kill-switch client, which deactivates
    all trading segments in a single call.  Upstox does not have a
    dedicated ``/exitall`` endpoint (unlike Dhan), so segment-wide
    deactivation is the closest equivalent.

    Return type is a plain dict matching the shape callers expect
    from the Dhan ExitAllAdapter (``success``, ``positions_closed``,
    ``orders_cancelled``, ``message``).
    """

    def __init__(self, kill_switch_client: UpstoxKillSwitchClient) -> None:
        self._kill_switch = kill_switch_client

    def exit_all(self) -> dict[str, Any]:
        """Deactivate all trading segments via the kill switch.

        Returns:
            dict with keys: ``success`` (bool), ``positions_closed`` (int),
            ``orders_cancelled`` (int), ``message`` (str), ``raw`` (dict).

        Raises:
            ExitAllError: If the kill-switch API call fails.
        """
        updates = [{"segment": "ALL", "status": "DEACTIVATE"}]
        try:
            result = self._kill_switch.set_status(updates)
        except Exception as exc:
            logger.warning("exit_all_failed", extra={"error": str(exc)})
            raise ExitAllError(f"Exit all operation failed: {exc}") from exc

        logger.info("exit_all_executed", extra={"result": result})
        # Upstox kill-switch doesn't return per-position/order counts,
        # so these are always 0 (documented in the return dict).
        return {
            "success": True,
            "positions_closed": 0,
            "orders_cancelled": 0,
            "message": "All segments deactivated via kill switch",
            "raw": result,
        }

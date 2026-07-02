"""Dhan session manager — unified view of auth, connection, and subscriptions."""

from __future__ import annotations

import logging
from typing import Any

from brokers.common.auth import AuthManager

logger = logging.getLogger(__name__)


class DhanSessionManager:
    """Consolidates auth readiness, WS health, and subscription snapshot."""

    def __init__(self, connection: Any, auth: AuthManager | None = None) -> None:
        self._conn = connection
        self._auth = auth

    @property
    def auth(self) -> AuthManager | None:
        return self._auth

    def token_valid(self) -> bool:
        if self._auth is None:
            return bool(getattr(self._conn, "access_token", ""))
        state = getattr(self._auth, "state", None)
        if state is None:
            return False
        is_valid = getattr(state, "is_valid", None)
        return bool(is_valid()) if callable(is_valid) else bool(state)

    def connection_state(self) -> dict[str, bool]:
        """Transport connectivity per stream kind."""
        state: dict[str, bool] = {}
        mf = getattr(self._conn, "market_feed", None)
        os_ = getattr(self._conn, "order_stream", None)
        state["market_feed"] = bool(mf and mf.is_connected)
        state["order_stream"] = bool(os_ and os_.is_connected)
        return state

    def subscription_snapshot(self) -> dict[str, Any]:
        """Authoritative subscription/callback counts."""
        engine = getattr(self._conn, "subscription_engine", None)
        if engine is not None:
            return {
                "instruments": engine.instrument_snapshot(),
                "subscription_count": engine.subscription_count(),
                "callback_count": engine.callback_count(),
            }
        return {"instruments": {}, "subscription_count": 0, "callback_count": 0}

    def lifecycle_state(self) -> str:
        """Coarse session state for dashboards."""
        if not self.token_valid():
            return "AUTH_REQUIRED"
        conn = self.connection_state()
        if not any(conn.values()):
            return "DISCONNECTED"
        if all(conn.values()):
            return "HEALTHY"
        return "DEGRADED"

    def is_ready_for_trading(self) -> bool:
        return self.token_valid() and self.connection_state().get("order_stream", False)

    def health_summary(self) -> dict[str, Any]:
        return {
            "lifecycle_state": self.lifecycle_state(),
            "token_valid": self.token_valid(),
            "connections": self.connection_state(),
            "subscriptions": self.subscription_snapshot(),
        }

"""Session management — connection lifecycle and state tracking."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional



class SessionStatus(Enum):
    """Session lifecycle states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSING = "closing"
    ERROR = "error"


@dataclass
class SessionInfo:
    """Current session information."""

    status: SessionStatus = SessionStatus.DISCONNECTED
    broker: str = ""
    account_id: str = ""
    connected_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    disconnect_count: int = 0
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionManager:
    """Manages the broker connection lifecycle.

    Tracks connection state, handles reconnection,
    and provides session health monitoring.
    """

    def __init__(self, broker: str = "") -> None:
        self._info = SessionInfo(broker=broker)
        self._lock = asyncio.Lock()
        self._state_callbacks: list[Any] = []
        self._reconnect_attempts = 0
        self._max_reconnect = 10
        self._reconnect_delay = 1.0

    @property
    def info(self) -> SessionInfo:
        return self._info

    @property
    def is_connected(self) -> bool:
        return self._info.status == SessionStatus.CONNECTED

    @property
    def status(self) -> SessionStatus:
        return self._info.status

    def on_state_change(self, callback: Any) -> None:
        """Register a state change callback."""
        self._state_callbacks.append(callback)

    async def transition(self, new_status: SessionStatus, error: Optional[str] = None) -> None:
        """Transition to a new session state."""
        async with self._lock:
            old_status = self._info.status
            self._info.status = new_status

            if new_status == SessionStatus.CONNECTED:
                self._info.connected_at = datetime.now(timezone.utc)
                self._info.error = None
                self._reconnect_attempts = 0
            elif new_status == SessionStatus.DISCONNECTED:
                self._info.disconnect_count += 1
            elif new_status == SessionStatus.ERROR:
                self._info.error = error

            for cb in self._state_callbacks:
                try:
                    await cb(old_status, new_status)
                except Exception:
                    pass

    async def heartbeat(self) -> None:
        """Record a heartbeat."""
        self._info.last_heartbeat = datetime.now(timezone.utc)

    async def get_reconnect_delay(self) -> float:
        """Calculate next reconnect delay with exponential backoff."""
        if self._reconnect_attempts >= self._max_reconnect:
            return -1  # Signal to stop reconnecting

        delay = self._reconnect_delay * (2**self._reconnect_attempts)
        self._reconnect_attempts += 1
        return min(delay, 60.0)

    def reset_reconnect(self) -> None:
        """Reset reconnect counter after successful connection."""
        self._reconnect_attempts = 0

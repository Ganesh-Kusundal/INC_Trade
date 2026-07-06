"""ConnectedGuard mixin — connection state management for broker adapters.

Provides a consistent ``is_connected`` property and ``require_connected()``
guard method that all adapters inherit. Eliminates the duplicated
``_require_connected()`` pattern across DhanAdapter, UpstoxAdapter,
and PaperAdapter.

Usage::

    from brokers_core.adapters.base import ConnectedGuard

    class DhanAdapter(ConnectedGuard):
        _adapter_name = "DhanAdapter"

        def connect(self):
            # ... setup ...
            self._connected = True

        def disconnect(self):
            # ... cleanup ...
            self._connected = False

        def quote(self, symbol, exchange):
            self.require_connected()  # Raises ConnectionError if not connected
            return self._market_data.quote(symbol, exchange)

All adapters inherit from ``ConnectedGuard`` which provides:
- ``_connected: bool`` — connection state flag
- ``is_connected: bool`` — property for checking connection
- ``require_connected()`` — raises ``ConnectionError`` if not connected
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ConnectedGuard:
    """Mixin providing connection state management for broker adapters.

    Subclasses should:
    1. Set ``_adapter_name`` to a human-readable name (e.g., ``"DhanAdapter"``)
    2. Set ``_connected = True`` in ``connect()``
    3. Set ``_connected = False`` in ``disconnect()``
    4. Call ``self.require_connected()`` at the start of provider methods

    Attributes:
        _connected: Whether the adapter is currently connected.
        _adapter_name: Human-readable adapter name for error messages.
    """

    _connected: bool = False
    _adapter_name: str = "Adapter"

    @property
    def is_connected(self) -> bool:
        """Check if the adapter is currently connected to the broker.

        Returns:
            True if connected, False otherwise.
        """
        return self._connected

    def require_connected(self) -> None:
        """Raise ``ConnectionError`` if the adapter is not connected.

        Call this at the start of every provider method (``quote()``,
        ``place_order()``, etc.) to ensure the adapter is in a valid
        state before making broker API calls.

        Raises:
            ConnectionError: If the adapter is not connected.
        """
        if not self._connected:
            msg = (
                f"{self._adapter_name} not connected. "
                f"Call connect() first."
            )
            logger.warning(
                "adapter_not_connected",
                extra={"adapter": self._adapter_name},
            )
            raise ConnectionError(msg)


__all__ = [
    "ConnectedGuard",
]

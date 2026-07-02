"""Margin provider port for risk management.

Defines the interface for margin calculation, implemented by broker adapters.
The risk manager depends on this port, not on broker-specific implementations.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MarginProviderPort(Protocol):
    """Protocol for margin calculation providers.

    Broker adapters implement this interface to provide margin data
    to the risk manager. The risk manager depends only on this port,
    not on broker-specific implementations.
    """

    def calculate_margin_for_order(self, order: Any) -> Any:
        """Calculate margin required for a given order.

        Parameters
        ----------
        order : Any
            Order request object.

        Returns
        -------
        Any
            Margin calculation result with required_margin field.
        """
        ...

"""ExecutionRouter — routes orders to broker adapters by account_id.

Account ID format: ``{broker_id}/{account_name}``
Example: ``dhan/default``, ``upstox/main``

The router extracts the broker_id from the account_id and routes
to the registered OrderExecutionPort for that broker.

Architecture: depends ONLY on ports/ (OrderExecutionPort).
NEVER imports: services/, adapters/, infrastructure/
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from inc_trade.domain.exceptions import BrokerError

logger = logging.getLogger(__name__)


class ExecutionRouter:
    """Routes orders to the correct broker adapter based on account_id.

    Supports:
    - Account-based routing (primary)
    - Health-aware fallback (circuit breaker integration)
    - Multi-account per broker
    - Preferred broker override

    Architecture: depends ONLY on ports/ (OrderExecutionPort).
    NEVER imports: services/, adapters/, infrastructure/
    """

    def __init__(self) -> None:
        # broker_id -> OrderExecutionPort
        self._providers: dict[str, Any] = {}
        # broker_id -> health check callable () -> bool
        self._health_checks: dict[str, Callable[[], bool]] = {}
        # Fallback order (when primary broker is unhealthy)
        self._fallback_order: list[str] = []

    def register(
        self,
        broker_id: str,
        provider: Any,
        health_check: Callable[[], bool] | None = None,
    ) -> None:
        """Register a broker's execution provider.

        Args:
            broker_id: Broker identifier (e.g., "dhan", "upstox").
            provider: OrderExecutionPort implementation.
            health_check: Optional callable returning True if healthy.
        """
        self._providers[broker_id] = provider
        if health_check:
            self._health_checks[broker_id] = health_check

    def set_fallback_order(self, broker_ids: list[str]) -> None:
        """Set the fallback chain for routing.

        Args:
            broker_ids: Ordered list of broker_ids to try.
                Example: ["dhan", "upstox", "paper"]
        """
        self._fallback_order = list(broker_ids)

    def route(self, account_id: str) -> Any:
        """Route to the correct broker based on account_id.

        Parses ``{broker_id}/{account_name}`` from account_id.
        Falls back through the fallback chain if primary is unhealthy.

        Args:
            account_id: Account identifier in ``{broker_id}/{account_name}`` format.

        Returns:
            OrderExecutionPort for the target broker.

        Raises:
            KeyError: If no broker can be found for the account_id.
            BrokerError: If all brokers in the fallback chain are unhealthy.
        """
        broker_id = self._parse_broker_id(account_id)

        # Try primary
        if broker_id in self._providers:
            if self._is_healthy(broker_id):
                return self._providers[broker_id]
            # Primary unhealthy, try fallback
            logger.warning("Primary broker %s unhealthy", broker_id)

        # Try fallback chain
        for fallback_id in self._fallback_order:
            if fallback_id in self._providers and self._is_healthy(fallback_id):
                logger.warning(
                    "Primary broker %s unhealthy, falling back to %s",
                    broker_id, fallback_id,
                )
                return self._providers[fallback_id]

        # Nothing available
        raise BrokerError(
            f"No healthy broker available for account {account_id}. "
            f"Tried: {broker_id} + fallback {self._fallback_order}"
        )

    def _parse_broker_id(self, account_id: str) -> str:
        """Extract broker_id from account_id.

        Format: ``{broker_id}/{account_name}``
        Example: ``dhan/default`` -> ``dhan``

        Raises:
            ValueError: If account_id doesn't match expected format.
        """
        if "/" not in account_id:
            raise ValueError(
                f"Invalid account_id format: {account_id!r}. "
                f"Expected '{{broker_id}}/{{account_name}}'"
            )
        broker_id, _, _ = account_id.partition("/")
        return broker_id

    def _is_healthy(self, broker_id: str) -> bool:
        """Check if a broker is healthy."""
        check = self._health_checks.get(broker_id)
        if check is None:
            return True  # No health check = assume healthy
        return check()

    @property
    def registered_brokers(self) -> list[str]:
        """List of registered broker IDs."""
        return list(self._providers.keys())

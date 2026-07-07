"""RiskPolicy — concrete strategy implementations for pre-trade risk gating.

Implements the :class:`RiskPolicyProtocol` defined in ``domain/account.py``.
The domain layer defines the protocol; this module provides concrete
implementations.  This preserves domain purity — ``domain/`` does not
import from ``brokers.risk``.

Injected into :class:`Account`.  ``Account.place_order()`` calls
``risk_policy.check()`` before executing.  If denied, returns
``OrderResponse.fail()``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import TYPE_CHECKING

from brokers.domain.account import RiskDecision, RiskPolicyProtocol
from brokers.domain.requests import OrderRequest

if TYPE_CHECKING:
    from brokers.provider.protocol import ExecutionProvider, MarketDataProvider


class RiskPolicy(ABC, RiskPolicyProtocol):
    """Abstract strategy for pre-trade risk checks.

    Implements the domain-local :class:`RiskPolicyProtocol`.
    Concrete implementations check order requests against risk limits
    before they reach the provider.

    This is a Strategy — it's called inside ``Account.place_order()``,
    not wrapped around the account.
    """

    @abstractmethod
    async def check(
        self,
        request: OrderRequest,
        provider: ExecutionProvider,
    ) -> RiskDecision:
        """Check if an order request is allowed.

        Args:
            provider: The execution provider. May also implement
                ``MarketDataProvider`` for notional-value checks.
        """
        ...

    @staticmethod
    def no_limits() -> RiskPolicy:
        """A policy that allows everything (for paper trading/testing)."""
        return _NoLimitsPolicy()

    @staticmethod
    def max_position(
        max_quantity: int,
        max_notional: Decimal | None = None,
    ) -> RiskPolicy:
        """Policy that limits position size and notional value."""
        return _MaxPositionPolicy(
            max_quantity=max_quantity,
            max_notional=max_notional or Decimal("0"),
        )


class _NoLimitsPolicy(RiskPolicy):
    """Allows all orders — used for paper trading and testing."""

    async def check(
        self,
        request: OrderRequest,
        provider: ExecutionProvider,
    ) -> RiskDecision:
        return RiskDecision.allow()


class _MaxPositionPolicy(RiskPolicy):
    """Limits order quantity and notional value."""

    __slots__ = ("_max_notional", "_max_quantity")

    def __init__(
        self,
        max_quantity: int,
        max_notional: Decimal,
    ) -> None:
        self._max_quantity = max_quantity
        self._max_notional = max_notional

    async def check(
        self,
        request: OrderRequest,
        provider: ExecutionProvider,
    ) -> RiskDecision:
        # Check quantity limit
        if request.quantity > self._max_quantity:
            return RiskDecision.deny(
                rule="MAX_QUANTITY",
                value=Decimal(str(request.quantity)),
                limit=Decimal(str(self._max_quantity)),
            )

        # Check notional limit (if set)
        if self._max_notional > 0:
            try:
                from brokers.domain.instrument import Instrument

                if not isinstance(provider, MarketDataProvider):
                    return RiskDecision.allow()  # Can't check notional
                inst = Instrument(
                    request.symbol,
                    request.exchange,
                    provider=provider,
                )
                ltp = await provider.get_ltp(inst)
                notional = ltp * Decimal(str(request.quantity))
                if notional > self._max_notional:
                    return RiskDecision.deny(
                        rule="MAX_NOTIONAL",
                        value=notional,
                        limit=self._max_notional,
                    )
            except Exception:
                # If we can't get LTP, allow the order (fail-open)
                pass

        return RiskDecision.allow()


__all__ = [
    "RiskDecision",
    "RiskPolicy",
]

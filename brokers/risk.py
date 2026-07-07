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

import logging
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import TYPE_CHECKING, cast

from brokers.domain.account import RiskDecision, RiskPolicyProtocol
from brokers.domain.capabilities import Capability
from brokers.domain.instrument import Instrument
from brokers.domain.requests import OrderRequest

if TYPE_CHECKING:
    from brokers.provider.protocol import ExecutionProvider, MarketDataProvider, Provider

logger = logging.getLogger(__name__)


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
        *,
        fail_open: bool = False,
    ) -> RiskPolicy:
        """Policy that limits position size and notional value.

        Args:
            max_quantity: Maximum allowed order quantity.
            max_notional: Maximum allowed notional value (LTP * quantity).
            fail_open: If True, allow orders when risk checks fail (e.g. can't
                fetch LTP). If False (default, safer), deny the order.
        """
        return _MaxPositionPolicy(
            max_quantity=max_quantity,
            max_notional=max_notional or Decimal("0"),
            fail_open=fail_open,
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

    __slots__ = ("_fail_open", "_max_notional", "_max_quantity")

    def __init__(
        self,
        max_quantity: int,
        max_notional: Decimal,
        *,
        fail_open: bool = False,
    ) -> None:
        self._max_quantity = max_quantity
        self._max_notional = max_notional
        self._fail_open = fail_open

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
                if not provider.capabilities.supports(Capability.MARKET_DATA):
                    return RiskDecision.allow()  # Can't check notional
                full_provider = cast("Provider", provider)
                inst = request.instrument or Instrument(
                    request.symbol,
                    request.exchange,
                    provider=full_provider,
                )
                ltp = await full_provider.get_ltp(inst)
                notional = ltp * Decimal(str(request.quantity))
                if notional > self._max_notional:
                    return RiskDecision.deny(
                        rule="MAX_NOTIONAL",
                        value=notional,
                        limit=self._max_notional,
                    )
            except Exception as exc:
                logger.warning(
                    "risk_check_error",
                    extra={"rule": "MAX_NOTIONAL", "error": str(exc)[:200], "fail_open": self._fail_open},
                )
                if self._fail_open:
                    pass  # Legacy behavior: allow order when we can't verify
                else:
                    return RiskDecision.deny(
                        rule="MAX_NOTIONAL_CHECK_FAILED",
                        value=Decimal("0"),
                        limit=self._max_notional,
                    )

        return RiskDecision.allow()


__all__ = [
    "RiskDecision",
    "RiskPolicy",
]

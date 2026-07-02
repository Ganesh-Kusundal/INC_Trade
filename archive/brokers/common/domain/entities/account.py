"""Account domain entities — Balance and FundLimits.

FundLimits has been consolidated into Balance. FundLimits is now
a type alias for backward compatibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(slots=True, frozen=True)
class Balance:
    """Canonical account balance — returned by every broker adapter.

    Consolidated from the former ``FundLimits`` class.
    All ``FundLimits`` fields are a subset of ``Balance``.
    """

    available_balance: Decimal = Decimal("0")
    used_margin: Decimal = Decimal("0")
    total_margin: Decimal = Decimal("0")
    sod_limit: Decimal = Decimal("0")
    collateral_amount: Decimal = Decimal("0")
    utilized_amount: Decimal = Decimal("0")
    withdrawable_balance: Decimal = Decimal("0")

    def has_sufficient(self, required: Decimal) -> bool:
        """Return True if available balance covers the required amount."""
        return self.available_balance >= required


# FundLimits is a type alias for Balance.
# All FundLimits fields (available_balance, used_margin, total_margin)
# are a subset of Balance. The has_sufficient() method was moved to Balance.
FundLimits = Balance

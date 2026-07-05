"""Rich value objects for extended instrument data.

These are immutable domain value objects with zero infrastructure deps.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Fundamentals:
    """Fundamental data for an equity instrument.

    Attributes:
        pe_ratio: Price-to-earnings ratio.
        dividend_yield: Annual dividend yield as percentage.
        market_cap: Market capitalization.
        eps: Earnings per share.
        book_value: Book value per share.
        roe: Return on equity (percentage).
        debt_to_equity: Debt-to-equity ratio.
    """

    pe_ratio: Decimal = Decimal("0")
    dividend_yield: Decimal = Decimal("0")
    market_cap: Decimal = Decimal("0")
    eps: Decimal = Decimal("0")
    book_value: Decimal = Decimal("0")
    roe: Decimal = Decimal("0")
    debt_to_equity: Decimal = Decimal("0")


@dataclass(frozen=True)
class Greeks:
    """Option greeks value object.

    Attributes:
        delta: Rate of change of option price w.r.t. underlying.
        gamma: Rate of change of delta w.r.t. underlying.
        theta: Rate of change of option price w.r.t. time.
        vega: Rate of change of option price w.r.t. volatility.
        rho: Rate of change of option price w.r.t. interest rate.
        iv: Implied volatility.
    """

    delta: Decimal = Decimal("0")
    gamma: Decimal = Decimal("0")
    theta: Decimal = Decimal("0")
    vega: Decimal = Decimal("0")
    rho: Decimal = Decimal("0")
    iv: Decimal = Decimal("0")


@dataclass(frozen=True)
class CorporateAction:
    """Corporate action event data.

    Attributes:
        action_type: Type of action (dividend, split, bonus, etc.).
        symbol: Affected symbol.
        ex_date: Ex-date for the action.
        record_date: Record date.
        value: Action value (dividend amount, split ratio, etc.).
        description: Human-readable description.
    """

    action_type: str = ""
    symbol: str = ""
    ex_date: str = ""
    record_date: str = ""
    value: Decimal = Decimal("0")
    description: str = ""

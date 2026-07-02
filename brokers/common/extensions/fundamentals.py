"""FundamentalsProvider extension interface.

Capability gate: ``BrokerCapabilities.supports_fundamentals``
Supported by: Upstox (P&L, balance sheet, cash flow, ratios)
Not supported by: Dhan
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from brokers.common.broker_port import QuotaToken


@dataclass(frozen=True)
class FinancialStatement:
    """A single period's financial statement data.

    period     — reporting period, e.g. ``"Q3FY25"`` or ``"FY24"``.
    period_type — ``"quarterly"`` or ``"annual"``.
    values     — dict mapping metric name to Decimal value.
    currency   — ISO 4217 currency code, e.g. ``"INR"``.
    """

    period: str
    period_type: str
    values: dict[str, Decimal]
    currency: str = "INR"


@dataclass(frozen=True)
class FundamentalsSnapshot:
    """Normalized fundamentals data for an instrument.

    isin     — ISIN of the instrument.
    symbol   — canonical symbol.
    pe_ratio / pb_ratio / eps — key ratios.
    statements — P&L / balance sheet / cash flow data by period.
    broker_id — which broker provided this data.
    """

    isin: str
    symbol: str
    broker_id: str
    pe_ratio: Decimal | None = None
    pb_ratio: Decimal | None = None
    eps: Decimal | None = None
    market_cap: Decimal | None = None
    dividend_yield: Decimal | None = None
    statements: tuple[FinancialStatement, ...] = field(default_factory=tuple)


class FundamentalsProvider(Protocol):
    """Extension interface for fundamental financial data.

    Brokers that do not support fundamentals raise ``UnsupportedExtensionError``
    when resolved through ``ExtensionRegistry``.
    """

    async def fetch_fundamentals(
        self,
        isin: str,
        *,
        quota: QuotaToken,
    ) -> FundamentalsSnapshot:
        """Fetch fundamental data for an instrument by ISIN."""
        ...

    async def fetch_financials(
        self,
        isin: str,
        statement_type: str,
        *,
        quota: QuotaToken,
        periods: int = 4,
    ) -> Sequence[FinancialStatement]:
        """Fetch P&L, balance sheet, or cash flow statements.

        statement_type — ``"profit_loss"``, ``"balance_sheet"``, or ``"cash_flow"``.
        """
        ...

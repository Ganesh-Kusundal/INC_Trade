"""MarketIntelligenceProvider extension interface.

Capability gate: ``Capability.MARKET_INTELLIGENCE`` / ``Capability.OI_PCR_MAXPAIN``
Supported by: Upstox (PCR, max pain, OI analysis, FII/DII flows, smartlists)
Not supported by: Dhan

These are enrichment features — they should never be requested on
execution-critical paths.  Route enrichment operations through
``SourceSelectionPolicy.enrichment`` and use ENRICHMENT priority quota.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class OiAnalysis:
    """Open interest analysis snapshot."""

    underlying: str
    expiry: str
    put_call_ratio: Decimal | None
    max_pain_strike: Decimal | None
    total_call_oi: int
    total_put_oi: int
    broker_id: str


@dataclass(frozen=True)
class FiiDiiActivity:
    """FII/DII cash market activity for a trading day."""

    date: str
    fii_buy: Decimal
    fii_sell: Decimal
    dii_buy: Decimal
    dii_sell: Decimal
    broker_id: str


@dataclass(frozen=True)
class Smartlist:
    """Broker-curated instrument watchlist."""

    list_name: str
    instruments: tuple[str, ...]
    broker_id: str


class MarketIntelligenceProvider(Protocol):
    """Extension interface for enrichment / market intelligence data."""

    async def fetch_oi_analysis(
        self,
        underlying: str,
        expiry: str,
        *,
        quota: object,
    ) -> OiAnalysis: ...

    async def fetch_fii_dii(
        self,
        *,
        quota: object,
        limit: int = 10,
    ) -> list[FiiDiiActivity]: ...

    async def fetch_smartlists(
        self,
        *,
        quota: object,
    ) -> list[Smartlist]: ...

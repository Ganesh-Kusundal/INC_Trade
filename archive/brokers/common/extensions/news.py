"""NewsProvider extension interface.

Capability gate: ``BrokerCapabilities.supports_news``
Supported by: Upstox
Not supported by: Dhan
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from brokers.common.broker_port import QuotaToken


@dataclass(frozen=True)
class NewsItem:
    """Normalized news article from a broker's news API.

    headline   — article headline.
    summary    — short description or first paragraph.
    symbols    — list of instrument symbols this article relates to.
    published_at — publication datetime (UTC, timezone-aware).
    category   — e.g. ``"company"``, ``"market"``, ``"sector"``.
    url        — optional link to the full article.
    source     — news publisher name.
    broker_id  — which broker provided this news item.
    """

    headline: str
    published_at: datetime
    broker_id: str
    summary: str = ""
    symbols: tuple[str, ...] = field(default_factory=tuple)
    category: str = ""
    url: str | None = None
    source: str = ""


class NewsProvider(Protocol):
    """Extension interface for broker news feeds.

    Brokers that do not support news raise ``UnsupportedExtensionError`` when
    the caller attempts to resolve this extension through ``ExtensionRegistry``.
    """

    async def fetch_symbol_news(
        self,
        symbol: str,
        *,
        quota: QuotaToken,
        limit: int = 20,
    ) -> Sequence[NewsItem]:
        """Fetch recent news items for a single instrument symbol."""
        ...

    async def fetch_market_news(
        self,
        *,
        quota: QuotaToken,
        category: str | None = None,
        limit: int = 20,
    ) -> Sequence[NewsItem]:
        """Fetch general market news, optionally filtered by category."""
        ...

"""Upstox extension providers for ExtensionRegistry."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from decimal import Decimal

from brokers.common.broker_port import QuotaToken
from brokers.common.extensions import ExtensionBundle
from brokers.common.extensions.forever_order import (
    ForeverOrderProvider,
    ForeverOrderRequest,
    ForeverOrderResult,
)
from brokers.common.extensions.fundamentals import (
    FinancialStatement,
    FundamentalsProvider,
    FundamentalsSnapshot,
)
from brokers.common.extensions.news import NewsItem, NewsProvider
from brokers.common.gateway import MarketDataGateway


class UpstoxNewsExtension(NewsProvider):
    def __init__(self, gateway: MarketDataGateway) -> None:
        broker = getattr(gateway, "_broker", None)
        if broker is None:
            raise RuntimeError("Upstox gateway missing _broker reference")
        self._news = broker.news

    async def fetch_symbol_news(
        self, symbol: str, *, quota: QuotaToken, limit: int = 20
    ) -> Sequence[NewsItem]:
        raw_items = self._news.get_news(symbol=symbol)
        return self._normalize(raw_items[:limit])

    async def fetch_market_news(
        self, *, quota: QuotaToken, category: str | None = None, limit: int = 20
    ) -> Sequence[NewsItem]:
        raw_items = self._news.get_news(category=category or "holdings")
        return self._normalize(raw_items[:limit])

    @staticmethod
    def _normalize(raw_items: list) -> list[NewsItem]:
        items: list[NewsItem] = []
        for row in raw_items:
            if not isinstance(row, dict):
                continue
            published = row.get("timestamp") or row.get("published_at")
            if isinstance(published, str):
                try:
                    published_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except ValueError:
                    published_at = datetime.now(tz=timezone.utc)
            else:
                published_at = datetime.now(tz=timezone.utc)
            items.append(
                NewsItem(
                    headline=str(row.get("headline") or row.get("title") or ""),
                    published_at=published_at,
                    broker_id="upstox",
                    summary=str(row.get("summary") or row.get("description") or ""),
                    symbols=tuple(row.get("symbols") or []),
                    category=str(row.get("category") or ""),
                    source=str(row.get("source") or ""),
                )
            )
        return items


class UpstoxFundamentalsExtension(FundamentalsProvider):
    def __init__(self, gateway: MarketDataGateway) -> None:
        self._extended = gateway.extended

    async def fetch_fundamentals(self, isin: str, *, quota: QuotaToken) -> FundamentalsSnapshot:
        ratios = self._extended.get_ratios(isin) if hasattr(self._extended, "get_ratios") else {}
        return FundamentalsSnapshot(
            isin=isin,
            symbol=isin,
            broker_id="upstox",
            pe_ratio=Decimal(str(ratios.get("pe", 0))) if ratios.get("pe") else None,
            pb_ratio=Decimal(str(ratios.get("pb", 0))) if ratios.get("pb") else None,
        )

    async def fetch_financials(
        self,
        isin: str,
        statement_type: str,
        *,
        quota: QuotaToken,
        periods: int = 4,
    ) -> Sequence[FinancialStatement]:
        fetcher = {
            "profit_loss": getattr(self._extended, "get_profit_loss", None),
            "balance_sheet": getattr(self._extended, "get_balance_sheet", None),
            "cash_flow": getattr(self._extended, "get_cash_flow", None),
        }.get(statement_type)
        if fetcher is None:
            return []
        rows = fetcher(isin) or []
        statements: list[FinancialStatement] = []
        for row in rows[:periods]:
            if not isinstance(row, dict):
                continue
            statements.append(
                FinancialStatement(
                    period=str(row.get("period", "")),
                    period_type=str(row.get("period_type", "annual")),
                    values={
                        k: Decimal(str(v))
                        for k, v in row.items()
                        if k not in {"period", "period_type"} and v is not None
                    },
                )
            )
        return statements


class UpstoxForeverOrderExtension(ForeverOrderProvider):
    def __init__(self, gateway: MarketDataGateway) -> None:
        broker = getattr(gateway, "_broker", None)
        if broker is None:
            raise RuntimeError("Upstox gateway missing _broker reference")
        self._gtt = broker.gtt

    async def place_forever_order(
        self, request: ForeverOrderRequest, *, quota: object
    ) -> ForeverOrderResult:
        return ForeverOrderResult(success=False, message="use Upstox GTT adapter directly")

    async def cancel_forever_order(self, order_id: str, *, quota: object) -> ForeverOrderResult:
        self._gtt.cancel_gtt(order_id)
        return ForeverOrderResult(success=True, order_id=order_id)

    async def modify_forever_order(
        self,
        order_id: str,
        *,
        price1: Decimal | None = None,
        trigger1: Decimal | None = None,
        price2: Decimal | None = None,
        trigger2: Decimal | None = None,
        quota: object,
    ) -> ForeverOrderResult:
        return ForeverOrderResult(success=False, message="not implemented")


def register_upstox_extensions(gateway: MarketDataGateway) -> ExtensionBundle:
    bundle = ExtensionBundle("upstox")
    bundle.register(NewsProvider, UpstoxNewsExtension(gateway))
    bundle.register(FundamentalsProvider, UpstoxFundamentalsExtension(gateway))
    bundle.register(ForeverOrderProvider, UpstoxForeverOrderExtension(gateway))
    return bundle


# Register factory so brokers.common.adapters can find it without importing us
from brokers.common.extensions import register_extension_factory

register_extension_factory("upstox", register_upstox_extensions)

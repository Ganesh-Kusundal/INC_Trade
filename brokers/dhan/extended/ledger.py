"""Dhan ledger — fetch account financial transaction history.

API: GET /ledger — get ledger entries
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """A single ledger entry (transaction)."""

    narration: str = ""
    traded_qty: int = 0
    instrument: str = ""
    segment: str = ""
    trade_id: str = ""
    order_id: str = ""
    trans_type: str = ""
    amount: float = 0.0
    balance: float = 0.0
    timestamp: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LedgerEntry:
        return cls(
            narration=str(data.get("narration", "")),
            traded_qty=int(data.get("tradedQty", 0) or 0),
            instrument=str(data.get("instrument", "")),
            segment=str(data.get("segment", "")),
            trade_id=str(data.get("tradeId", "")),
            order_id=str(data.get("orderId", "")),
            trans_type=str(data.get("transType", "")),
            amount=float(data.get("amount", 0) or 0),
            balance=float(data.get("balance", 0) or 0),
            timestamp=str(data.get("createTime", "")),
        )


class DhanLedger:
    """Ledger entry retrieval for Dhan.

    Usage::

        ledger = DhanLedger(client=dhan_client)
        entries = ledger.get_entries(from_date="2026-01-01", to_date="2026-06-30")
    """

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def get_entries(
        self,
        from_date: str = "2026-01-01",
        to_date: str = "2026-06-30",
    ) -> list[LedgerEntry]:
        """Get ledger entries for a date range."""
        endpoint = f"/ledger/{from_date}/{to_date}"
        data = self._client.get(endpoint)
        items = data.get("data", []) if isinstance(data, dict) else []
        if isinstance(items, list):
            return [LedgerEntry.from_dict(item) for item in items if isinstance(item, dict)]
        return []


__all__ = ["DhanLedger", "LedgerEntry"]

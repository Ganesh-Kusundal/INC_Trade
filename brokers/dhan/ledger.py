"""Ledger adapter — fetch account ledger entries."""

from __future__ import annotations

import logging
import re
from decimal import Decimal

from brokers.dhan.domain import LedgerEntry
from brokers.dhan.exceptions import LedgerError
from brokers.dhan.http_client import DhanHttpClient

logger = logging.getLogger(__name__)


class LedgerAdapter:
    """Adapter for Dhan Ledger API."""

    def __init__(self, client: DhanHttpClient):
        self._client = client

    def get_ledger(self, from_date: str, to_date: str) -> list[LedgerEntry]:
        """Get ledger entries for a date range.

        Args:
            from_date: Start date in YYYY-MM-DD format
            to_date: End date in YYYY-MM-DD format

        Returns:
            List of LedgerEntry objects

        Raises:
            ValueError: If date format is invalid
            LedgerError: If API call fails
        """
        # Validate date format
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        if not date_pattern.match(from_date):
            raise ValueError(f"Invalid from_date format: {from_date}. Expected YYYY-MM-DD")
        if not date_pattern.match(to_date):
            raise ValueError(f"Invalid to_date format: {to_date}. Expected YYYY-MM-DD")

        try:
            data = self._client.get(f"/ledger?from-date={from_date}&to-date={to_date}")
        except Exception as exc:
            raise LedgerError(f"Failed to fetch ledger: {exc}") from exc

        items = data.get("data", []) if isinstance(data, dict) else []
        entries = [self._parse_entry(item) for item in (items if isinstance(items, list) else [])]

        logger.info(
            "ledger_fetched",
            extra={
                "from_date": from_date,
                "to_date": to_date,
                "count": len(entries),
            },
        )
        return entries

    def _parse_entry(self, data: dict) -> LedgerEntry:
        """Parse ledger entry from API response."""
        return LedgerEntry(
            narration=data.get("narration", ""),
            voucher_date=data.get("voucherDate", ""),
            exchange=data.get("exchange", ""),
            voucher_description=data.get("voucherDescription", ""),
            voucher_number=data.get("voucherNumber", ""),
            debit=Decimal(str(data.get("debit", 0))),
            credit=Decimal(str(data.get("credit", 0))),
            running_balance=Decimal(str(data.get("runningBalance", 0))),
        )

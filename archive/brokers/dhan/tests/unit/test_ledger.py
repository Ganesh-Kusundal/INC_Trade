"""Unit tests for LedgerAdapter."""

from decimal import Decimal

import pytest

from brokers.dhan.ledger import LedgerAdapter


def test_get_ledger_payload(fake_client):
    """Verify GET /ledger?from-date=...&to-date=..."""
    fake_client.set_response("GET", "/ledger?from-date=2026-01-01&to-date=2026-01-31", {"data": []})
    adapter = LedgerAdapter(fake_client)
    adapter.get_ledger("2026-01-01", "2026-01-31")

    # Check the URL was constructed correctly
    calls = [c for c in fake_client.calls if c[0] == "GET" and "ledger" in c[1]]
    assert len(calls) == 1
    assert "from-date=2026-01-01" in calls[0][1]
    assert "to-date=2026-01-31" in calls[0][1]


def test_get_ledger_parsing(fake_client):
    """Verify response parsing to list[LedgerEntry]."""
    fake_client.set_response(
        "GET",
        "/ledger?from-date=2026-01-01&to-date=2026-01-31",
        {
            "data": [
                {
                    "narration": "Order Execution",
                    "voucherDate": "2026-01-15",
                    "exchange": "NSE",
                    "voucherDescription": "Buy RELIANCE",
                    "voucherNumber": "V001",
                    "debit": 24500.0,
                    "credit": 0.0,
                    "runningBalance": 75500.0,
                },
                {
                    "narration": "Credit",
                    "voucherDate": "2026-01-20",
                    "exchange": "NSE",
                    "voucherDescription": "Funds added",
                    "voucherNumber": "V002",
                    "debit": 0.0,
                    "credit": 50000.0,
                    "runningBalance": 125500.0,
                },
            ]
        },
    )
    adapter = LedgerAdapter(fake_client)
    entries = adapter.get_ledger("2026-01-01", "2026-01-31")

    assert len(entries) == 2
    assert entries[0].narration == "Order Execution"
    assert entries[0].voucher_date == "2026-01-15"
    assert entries[0].debit == Decimal("24500.0")
    assert entries[0].credit == Decimal("0.0")
    assert entries[0].running_balance == Decimal("75500.0")

    assert entries[1].narration == "Credit"
    assert entries[1].credit == Decimal("50000.0")


def test_get_ledger_empty(fake_client):
    """Verify empty response handling."""
    fake_client.set_response("GET", "/ledger?from-date=2026-01-01&to-date=2026-01-31", {"data": []})
    adapter = LedgerAdapter(fake_client)
    entries = adapter.get_ledger("2026-01-01", "2026-01-31")

    assert isinstance(entries, list)
    assert len(entries) == 0


def test_get_ledger_date_format(fake_client):
    """Verify date format validation (YYYY-MM-DD)."""
    adapter = LedgerAdapter(fake_client)

    with pytest.raises(ValueError) as exc_info:
        adapter.get_ledger("01-01-2026", "2026-01-31")  # Wrong format
    assert "date" in str(exc_info.value).lower()

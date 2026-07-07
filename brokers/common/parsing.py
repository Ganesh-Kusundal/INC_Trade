"""Shared parsing helpers — canonical implementations for value conversion.

Eliminates the duplicated _dec/_int/_parse_ts functions that existed in
brokers/dhan/mapper.py, brokers/upstox/mapper.py, and brokers/domain/values.py.

Usage::

    from brokers.common.parsing import dec, int_val, parse_ts
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any


def dec(val: Any) -> Decimal:
    """Parse a value to Decimal, returning Decimal('0') for missing/empty values.

    Used by broker mappers for safe numeric conversion from API responses.
    """
    if val is None or val == "":
        return Decimal("0")
    try:
        return Decimal(str(val))
    except (ValueError, TypeError):
        return Decimal("0")


def dec_optional(val: Any) -> Decimal | None:
    """Parse a value to Decimal, returning None for missing/empty values.

    Used when None has distinct meaning from zero (e.g., Greeks).
    """
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except (ValueError, TypeError):
        return None


def int_val(val: Any) -> int:
    """Parse a value to int, returning 0 for missing/empty values."""
    if val is None or val == "":
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def parse_ts(val: Any) -> datetime | None:
    """Parse a timestamp from various formats, returning None for missing values.

    Handles ISO format strings and datetime objects.
    """
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None


def parse_epoch(val: Any) -> datetime:
    """Parse a timestamp that may be an epoch integer or ISO string.

    Returns datetime.now(UTC) for None, empty, zero, negative, or
    out-of-range values. Used by Dhan historical APIs which return
    epoch integers.
    """
    if val is None or val == "":
        return datetime.now(tz=timezone.utc)
    # Epoch integer (int or float)
    if isinstance(val, (int, float)):
        if val <= 0:
            return datetime.now(tz=timezone.utc)
        try:
            return datetime.fromtimestamp(val, tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return datetime.now(tz=timezone.utc)
    val_str = str(val).strip()
    if not val_str or val_str == "0":
        return datetime.now(tz=timezone.utc)
    # Try numeric string (epoch)
    try:
        epoch = float(val_str)
        if epoch <= 0:
            return datetime.now(tz=timezone.utc)
        return datetime.fromtimestamp(epoch, tz=timezone.utc)
    except (ValueError, OSError, OverflowError):
        pass
    # Try ISO format
    try:
        return datetime.fromisoformat(val_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return datetime.now(tz=timezone.utc)


__all__ = [
    "dec",
    "dec_optional",
    "int_val",
    "parse_epoch",
    "parse_ts",
]

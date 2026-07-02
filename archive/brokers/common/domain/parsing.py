"""Shared parsing utilities — single source for type conversion helpers.

All broker adapters and domain models MUST import from this module
instead of duplicating parsing logic. These functions handle edge cases
like None, empty strings, and invalid values consistently.

Usage::

    from domain.parsing import parse_decimal, parse_int, parse_timestamp

    price = parse_decimal(raw_value, default=Decimal("0"))
    qty = parse_int(raw_qty, default=0)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def parse_optional_str(value: Any) -> str | None:
    """Convert value to string, returning None for None or empty string.

    Args:
        value: Any value to convert

    Returns:
        String representation, or None if value is None/empty
    """
    if value is None:
        return None
    s = str(value)
    return s if s else None


def parse_decimal(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    """Convert value to Decimal with safe fallback.

    Args:
        value: Any value to convert (string, int, float, etc.)
        default: Default value if conversion fails

    Returns:
        Decimal value, or default if conversion fails
    """
    if value is None or value == "":
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default


def parse_int(value: Any, default: int = 0) -> int:
    """Convert value to int with safe fallback.

    Args:
        value: Any value to convert (string, float, etc.)
        default: Default value if conversion fails

    Returns:
        Integer value, or default if conversion fails
    """
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def parse_timestamp(value: Any) -> datetime | None:
    """Parse timestamp from various formats.

    Handles:
    - ISO format strings (with Z timezone)
    - Unix timestamps (int/float)
    - None or empty values

    Args:
        value: Timestamp in any supported format

    Returns:
        Parsed datetime, or None if parsing fails
    """
    if not value:
        return None

    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(float(value))
        except (ValueError, OSError, OverflowError):
            return None

    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    return None

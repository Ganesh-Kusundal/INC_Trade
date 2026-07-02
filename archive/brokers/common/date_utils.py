"""Shared date-formatting utilities (REF-09 extraction).

Consolidates date parsing and formatting helpers that were duplicated
across broker adapters.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def format_expiry_components(expiry_str: str) -> tuple[str, str, str, str, str]:
    """Parse an ``%Y-%m-%d`` expiry string into formatted components.

    Returns
    -------
    tuple[str, str, str, str, str]
        ``(dd, dd_strip, mmm, yy, yyyy)`` where *dd_strip* is the
        day without zero-padding.
    """
    dt = datetime.strptime(expiry_str[:10], "%Y-%m-%d")
    dd = dt.strftime("%d")
    dd_strip = str(int(dd))
    mmm = dt.strftime("%b").upper()
    yy = dt.strftime("%y")
    yyyy = dt.strftime("%Y")
    return dd, dd_strip, mmm, yy, yyyy


def parse_expiry_date(value: Any) -> date | None:
    """Parse an expiry date from multiple common formats.

    Tries ``%Y-%m-%d``, ``%d%b%Y``, and ``%d-%b-%Y`` in order.
    Returns ``None`` if none match.
    """
    if not value:
        return None
    if isinstance(value, date):
        return value
    for fmt in ("%Y-%m-%d", "%d%b%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(str(value), fmt).date()
        except ValueError:
            continue
    return None

"""Enum canonicalization helpers (REF-06 extraction).

Consolidates the ``_canonicalize_order_enums`` static method that was
previously duplicated in spirit across broker adapters.  This utility
normalises domain enums or raw strings into uppercase wire strings.
"""

from __future__ import annotations

from typing import Any


def canonicalize_order_enums(
    side: str | Any,
    order_type: str | Any,
    product_type: str | Any,
    validity: str | Any,
) -> tuple[str, str, str, str]:
    """Canonicalise order enum / mixed values to uppercase strings.

    Accepts either domain enum instances (``Side.BUY``, ``OrderType.MARKET``,
    etc.) or raw strings.  Returns the tuple ``(side, order_type, product_type, validity)``
    as uppercase strings suitable for broker wire formats.
    """
    sv = side.value if _has_value(side) else str(side).upper()
    ot = order_type.value if _has_value(order_type) else str(order_type).upper()
    pt = (
        product_type.value
        if _has_value(product_type)
        else str(product_type).upper()
    )
    vl = validity.value if _has_value(validity) else str(validity).upper()
    return sv, ot, pt, vl


def _has_value(obj: Any) -> bool:
    """Check if *obj* has a ``.value`` attribute (i.e. is a domain enum)."""
    return hasattr(obj, "value")

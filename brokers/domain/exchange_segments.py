"""Typed exchange-segment helpers.

Single point of conversion between free-form exchange strings (user input,
log lines, broker payloads) and the canonical :class:`ExchangeSegment` enum.

Design rules
------------
* Functions accept ``str | ExchangeSegment`` and always return a
  :class:`ExchangeSegment` (or the ``default`` when no match).
* Aliases common in broker payloads (``"NSE"``, ``"BSE"``, ``"MCX"``)
  are normalised to the enum's wire-format value.
* :func:`is_equity_segment`, :func:`is_derivative_segment`, and
  :func:`is_currency_segment` are the canonical classification helpers.
"""

from __future__ import annotations

from enum import Enum


class ExchangeSegment(str, Enum):
    """Exchange segments supported by the broker system.

    The values use canonical wire-format strings (e.g. ``"NSE_EQ"``) so the
    segment string in the HTTP payload matches what the broker expects.
    """

    NSE = "NSE_EQ"
    BSE = "BSE_EQ"
    NSE_FNO = "NSE_FNO"
    BSE_FNO = "BSE_FNO"
    MCX = "MCXCOMM"
    NSE_CURRENCY = "NSE_CURRENCY"
    BSE_CURRENCY = "BSE_CURRENCY"
    IDX_I = "IDX_I"


# ── Aliases ────────────────────────────────────────────────────────────────
#
# Many adapters receive the human-friendly exchange identifier
# ("NSE", "BSE", "MCX") instead of the wire-format segment
# ("NSE_EQ", "BSE_EQ", "MCXCOMM"). The table below canonicalises
# the common short forms.
_ALIASES: dict[str, ExchangeSegment] = {
    "NSE": ExchangeSegment.NSE,
    "NSE_EQ": ExchangeSegment.NSE,
    "BSE": ExchangeSegment.BSE,
    "BSE_EQ": ExchangeSegment.BSE,
    "MCX": ExchangeSegment.MCX,
    "MCXCOMM": ExchangeSegment.MCX,
    "MCX_COMM": ExchangeSegment.MCX,
    "NSE_FNO": ExchangeSegment.NSE_FNO,
    "NFO": ExchangeSegment.NSE_FNO,
    "BSE_FNO": ExchangeSegment.BSE_FNO,
    "BFO": ExchangeSegment.BSE_FNO,
    "NSE_CURRENCY": ExchangeSegment.NSE_CURRENCY,
    "CDS": ExchangeSegment.NSE_CURRENCY,
    "BSE_CURRENCY": ExchangeSegment.BSE_CURRENCY,
    "BCD": ExchangeSegment.BSE_CURRENCY,
    "IDX_I": ExchangeSegment.IDX_I,
    "INDEX": ExchangeSegment.IDX_I,
}

# Derivative segments are NSE/BSE FNO, NSE/BSE currency, and MCX.
_DERIVATIVE_SEGMENTS: frozenset[ExchangeSegment] = frozenset(
    {
        ExchangeSegment.NSE_FNO,
        ExchangeSegment.BSE_FNO,
        ExchangeSegment.MCX,
        ExchangeSegment.NSE_CURRENCY,
        ExchangeSegment.BSE_CURRENCY,
    }
)
_EQUITY_SEGMENTS: frozenset[ExchangeSegment] = frozenset({ExchangeSegment.NSE, ExchangeSegment.BSE})
_CURRENCY_SEGMENTS: frozenset[ExchangeSegment] = frozenset(
    {ExchangeSegment.NSE_CURRENCY, ExchangeSegment.BSE_CURRENCY}
)

# Short exchange codes (NSE, NFO, MCX, …) for display and broker APIs.
_EXCHANGE_SHORT: dict[ExchangeSegment, str] = {
    ExchangeSegment.NSE: "NSE",
    ExchangeSegment.BSE: "BSE",
    ExchangeSegment.NSE_FNO: "NFO",
    ExchangeSegment.BSE_FNO: "BFO",
    ExchangeSegment.MCX: "MCX",
    ExchangeSegment.NSE_CURRENCY: "CDS",
    ExchangeSegment.BSE_CURRENCY: "BCD",
    ExchangeSegment.IDX_I: "IDX",
}


def parse_segment(
    value: str | ExchangeSegment,
    *,
    default: ExchangeSegment | None = None,
) -> ExchangeSegment | None:
    """Convert a free-form segment string to the canonical enum.

    Lookup is case-insensitive and aliases are resolved through
    :data:`_ALIASES`. Returns ``default`` (or ``None``) on no match
    so the caller can decide between "fall back" and "raise".

    Examples
    --------
    >>> parse_segment("NSE")
    <ExchangeSegment.NSE: 'NSE_EQ'>
    >>> parse_segment("nfo")
    <ExchangeSegment.NSE_FNO: 'NSE_FNO'>
    >>> parse_segment(ExchangeSegment.MCX)
    <ExchangeSegment.MCX: 'MCXCOMM'>
    >>> parse_segment("UNKNOWN")
    None
    """
    if isinstance(value, ExchangeSegment):
        return value
    if not isinstance(value, str):
        return default
    key = value.strip().upper()
    if key in _ALIASES:
        return _ALIASES[key]
    # Last-ditch: try the enum's own value lookup
    try:
        return ExchangeSegment(key)
    except ValueError:
        return default


def is_equity_segment(segment: str | ExchangeSegment) -> bool:
    """True if ``segment`` is an equity (NSE/BSE cash) segment."""
    parsed = parse_segment(segment)
    return parsed in _EQUITY_SEGMENTS


def is_derivative_segment(segment: str | ExchangeSegment) -> bool:
    """True if ``segment`` is a derivative (FNO, currency, commodity)."""
    parsed = parse_segment(segment)
    return parsed in _DERIVATIVE_SEGMENTS


def is_currency_segment(segment: str | ExchangeSegment) -> bool:
    """True if ``segment`` is a currency-derivatives segment."""
    parsed = parse_segment(segment)
    return parsed in _CURRENCY_SEGMENTS


def is_commodity_segment(segment: str | ExchangeSegment) -> bool:
    """True if ``segment`` is MCX (commodity derivatives)."""
    return parse_segment(segment) == ExchangeSegment.MCX


def wire_value(segment: str | ExchangeSegment) -> str:
    """Return the canonical wire-format string for a segment.

    Raises:
        ValueError: if ``segment`` is not a recognised exchange.
    """
    parsed = parse_segment(segment)
    if parsed is None:
        raise ValueError(f"Unknown exchange segment: {segment!r}")
    return parsed.value


def canonical_exchange_short(segment: str | ExchangeSegment) -> str:
    """Return the short exchange code (``NSE``, ``NFO``, ``MCX``, …) for *segment*."""
    parsed = parse_segment(segment)
    if parsed is None:
        raise ValueError(f"Unknown exchange segment: {segment!r}")
    return _EXCHANGE_SHORT[parsed]


__all__ = [
    "ExchangeSegment",
    "canonical_exchange_short",
    "is_commodity_segment",
    "is_currency_segment",
    "is_derivative_segment",
    "is_equity_segment",
    "parse_segment",
    "wire_value",
]

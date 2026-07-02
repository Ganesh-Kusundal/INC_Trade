"""Price arithmetic utilities for Indian equity markets.

Provides tick-size snapping, alignment checking, and controlled
Decimal-to-float conversion at the broker wire boundary.

All functions operate on ``Decimal`` to preserve the precision
guarantee that flows from API entry through domain logic to broker exit.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

_ZERO = Decimal("0")
_ONE = Decimal("1")


def snap_to_tick(price: Decimal, tick_size: Decimal) -> Decimal:
    """Round *price* to the nearest multiple of *tick_size*.

    Uses ``ROUND_HALF_UP`` — standard NSE/BSE convention where
    0.5 rounds away from zero.

    >>> snap_to_tick(Decimal("100.13"), Decimal("0.05"))
    Decimal('100.15')
    >>> snap_to_tick(Decimal("100.12"), Decimal("0.05"))
    Decimal('100.10')
    """
    if tick_size <= _ZERO:
        raise ValueError(f"tick_size must be positive, got {tick_size}")
    if price < _ZERO:
        raise ValueError(f"price must be non-negative, got {price}")
    if price == _ZERO:
        return _ZERO
    ticks = (price / tick_size).quantize(_ONE, rounding=ROUND_HALF_UP)
    return (ticks * tick_size).quantize(tick_size)


def is_tick_aligned(
    price: Decimal,
    tick_size: Decimal,
    *,
    tolerance: Decimal = Decimal("0.0001"),
) -> bool:
    """Return ``True`` if *price* is an exact multiple of *tick_size*.

    A small *tolerance* absorbs floating-point residue from upstream
    ``Decimal(str(float_value))`` conversions.

    >>> is_tick_aligned(Decimal("100.05"), Decimal("0.05"))
    True
    >>> is_tick_aligned(Decimal("100.07"), Decimal("0.05"))
    False
    """
    if tick_size <= _ZERO:
        raise ValueError(f"tick_size must be positive, got {tick_size}")
    if price < _ZERO:
        raise ValueError(f"price must be non-negative, got {price}")
    if price == _ZERO:
        return True
    remainder = price % tick_size
    return remainder <= tolerance or (tick_size - remainder) <= tolerance


def to_wire_float(price: Decimal, *, max_decimals: int = 4) -> float:
    """Convert *price* to ``float`` with explicit precision quantize.

    Quantizes to *max_decimals* decimal places **before** the float
    conversion so the wire value is deterministic and broker-friendly.

    >>> to_wire_float(Decimal("1234.56789"), max_decimals=2)
    1234.57
    """
    if max_decimals < 0:
        raise ValueError(f"max_decimals must be >= 0, got {max_decimals}")
    quantizer = Decimal(10) ** -max_decimals
    quantized = price.quantize(quantizer, rounding=ROUND_HALF_UP)
    return float(quantized)

"""Price parser: Upstox returns prices in **rupees** for V2/V3 REST and
**paise** for the binary WebSocket feed.

Mirrors Trade_J ``UpstoxPriceParser``.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

Number = int | float | str | Decimal


class UpstoxPriceParser:
    @staticmethod
    def parse(value: Number, *, is_paise: bool = False) -> Decimal:
        if value is None or value == "":
            return Decimal("0")
        decimal_value = Decimal(str(value))
        if is_paise:
            return (decimal_value / Decimal("100")).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_UP
            )
        return decimal_value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def to_paise(rupee: Number) -> int:
        decimal_value = UpstoxPriceParser.parse(rupee)
        return int((decimal_value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    @staticmethod
    def to_rupee(paise: int) -> Decimal:
        return (Decimal(paise) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

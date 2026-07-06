"""Volume Profile — Market Profile-style volume distribution.

The Volume Profile bins volume by price level. From this it derives:

- ``poc`` — Point of Control (price level with the highest volume).
- ``value_area`` — the price range that contains ``value_pct`` of
  total volume (default 70 %).
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal


class VolumeProfile:
    """Aggregate volume by price level and derive POC / Value Area.

    Args:
        value_pct: Percentage of total volume for the value area.
            Default 70 (i.e., 70 %).
        price_bucket: Bucket size for grouping prices. ``Decimal('0.5')``
            means prices are rounded to the nearest 0.5. Default
            ``Decimal('0.05')`` to match Indian equity tick size.
    """

    def __init__(
        self,
        value_pct: int = 70,
        price_bucket: Decimal = Decimal("0.05"),
    ) -> None:
        if not 0 < value_pct <= 100:
            raise ValueError("value_pct must be in (0, 100]")
        self._value_pct = value_pct
        self._bucket = price_bucket
        self._buckets: dict[Decimal, int] = defaultdict(int)
        self._total_volume = 0

    def update(self, price: Decimal, volume: int) -> None:
        """Add volume at a price level.

        Args:
            price: Price level.
            volume: Volume at this level.
        """
        if volume <= 0:
            return
        bucket = (price / self._bucket).to_integral_value() * self._bucket
        self._buckets[bucket] += volume
        self._total_volume += volume

    def update_candle(
        self, open_: Decimal, high: Decimal, low: Decimal, close: Decimal, volume: int
    ) -> None:
        """Distribute a candle's volume across its high-low range.

        For simplicity this puts the full volume at the midpoint.
        More sophisticated distributions can be added later.
        """
        if volume <= 0:
            return
        midpoint = (high + low) / Decimal("2")
        self.update(midpoint, volume)

    @property
    def poc(self) -> Decimal:
        """Point of Control — price with highest volume. ``Decimal('0')`` if empty."""
        if not self._buckets:
            return Decimal("0")
        best_price = max(self._buckets.items(), key=lambda kv: kv[1])[0]
        return best_price

    @property
    def value_area(self) -> tuple[Decimal, Decimal]:
        """Value area as ``(value_area_low, value_area_high)``.

        Walks outward from POC adding the highest-volume bucket at each
        step until cumulative volume >= value_pct of total. Returns
        ``(Decimal('0'), Decimal('0'))`` if empty.
        """
        if not self._buckets:
            return (Decimal("0"), Decimal("0"))
        target = self._total_volume * Decimal(self._value_pct) / Decimal("100")
        poc_price = self.poc
        accumulated = self._buckets[poc_price]
        lo = poc_price
        hi = poc_price
        sorted_prices = sorted(self._buckets.keys())
        left = sorted_prices.index(poc_price) - 1
        right = sorted_prices.index(poc_price) + 1
        while accumulated < target and (left >= 0 or right < len(sorted_prices)):
            left_vol = self._buckets[sorted_prices[left]] if left >= 0 else 0
            right_vol = self._buckets[sorted_prices[right]] if right < len(sorted_prices) else 0
            if right_vol >= left_vol and right < len(sorted_prices):
                accumulated += right_vol
                hi = sorted_prices[right]
                right += 1
            elif left >= 0:
                accumulated += left_vol
                lo = sorted_prices[left]
                left -= 1
            else:
                break
        return (lo, hi)

    @property
    def total_volume(self) -> int:
        """Total volume accumulated."""
        return self._total_volume

    def reset(self) -> None:
        """Clear all state."""
        self._buckets.clear()
        self._total_volume = 0

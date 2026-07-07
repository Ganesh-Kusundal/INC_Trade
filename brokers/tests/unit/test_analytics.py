"""Unit tests for the Analytics package."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from brokers.domain.entities import Candle, OptionLeg, Trade
from brokers.domain.enums import Side
from brokers.market.analytics.atr import ATRCalculator
from brokers.market.analytics.greeks import GreeksCalculator
from brokers.market.analytics.volume_profile import VolumeProfile
from brokers.market.analytics.vwap import VWAPCalculator


def _trade(price: Decimal, qty: int) -> Trade:
    return Trade(
        trade_id=f"T-{price}-{qty}",
        order_id="O-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        quantity=qty,
        price=price,
    )


class TestVWAP:
    def test_empty(self) -> None:
        v = VWAPCalculator()
        assert v.value == Decimal("0")
        assert v.trade_count == 0

    def test_single_trade(self) -> None:
        v = VWAPCalculator()
        v.update(_trade(Decimal("100"), 10))
        assert v.value == Decimal("100")
        assert v.trade_count == 1

    def test_weighted_average(self) -> None:
        v = VWAPCalculator()
        v.update(_trade(Decimal("100"), 10))  # pv=1000
        v.update(_trade(Decimal("200"), 10))  # pv=2000
        # total pv=3000, qty=20 → 150
        assert v.value == Decimal("150")
        assert v.cumulative_volume == 20

    def test_reset(self) -> None:
        v = VWAPCalculator()
        v.update(_trade(Decimal("100"), 10))
        v.reset()
        assert v.value == Decimal("0")
        assert v.trade_count == 0

    def test_zero_quantity_trade_ignored(self) -> None:
        v = VWAPCalculator()
        v.update(_trade(Decimal("100"), 0))
        assert v.trade_count == 0


class TestGreeks:
    def _leg(
        self,
        delta: Decimal | None = None,
        gamma: Decimal | None = None,
        theta: Decimal | None = None,
        vega: Decimal | None = None,
        iv: Decimal | None = None,
        symbol: str = "X",
    ) -> OptionLeg:
        return OptionLeg(
            ltp=Decimal("100"),
            oi=0,
            volume=0,
            iv=iv,
            delta=delta,
            theta=theta,
            gamma=gamma,
            vega=vega,
            security_id=None,
            symbol=symbol,
        )

    def test_single_leg(self) -> None:
        leg = self._leg(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            theta=Decimal("-0.1"),
            vega=Decimal("0.3"),
            iv=Decimal("20"),
        )
        out = GreeksCalculator.single_leg(leg)
        assert out["delta"] == Decimal("0.5")
        assert out["iv"] == Decimal("20")

    def test_portfolio_aggregation(self) -> None:
        leg1 = self._leg(
            delta=Decimal("0.5"),
            gamma=Decimal("0.02"),
            theta=Decimal("-0.1"),
            vega=Decimal("0.3"),
        )
        leg2 = self._leg(
            delta=Decimal("-0.3"),
            gamma=Decimal("0.01"),
            theta=Decimal("-0.05"),
            vega=Decimal("0.2"),
        )
        total = GreeksCalculator.portfolio_greeks([(leg1, 100), (leg2, 100)])
        assert total["delta"] == Decimal("20")
        assert total["theta"] == Decimal("-15")

    def test_portfolio_with_short(self) -> None:
        leg = self._leg(delta=Decimal("0.5"))
        total = GreeksCalculator.portfolio_greeks([(leg, 100), (leg, -50)])
        assert total["delta"] == Decimal("25")

    def test_portfolio_with_missing_greek(self) -> None:
        leg = self._leg(delta=None, gamma=Decimal("0.01"))
        total = GreeksCalculator.portfolio_greeks([(leg, 100)])
        assert total["delta"] == Decimal("0")
        assert total["gamma"] == Decimal("1")


class TestATR:
    def test_initial_zero(self) -> None:
        atr = ATRCalculator(period=3)
        assert atr.value == Decimal("0")
        assert not atr.is_ready

    def test_updates_with_candle(self) -> None:
        atr = ATRCalculator(period=3)
        c1 = Candle(
            symbol="X",
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("95"),
            close=Decimal("105"),
            volume=100,
        )
        atr.update(c1)
        assert atr.value == Decimal("15")  # high-low = 15
        assert not atr.is_ready

    def test_full_period_average(self) -> None:
        atr = ATRCalculator(period=3)
        base = datetime(2024, 1, 1, tzinfo=UTC)
        candles = [
            Candle(
                symbol="X",
                timestamp=base + timedelta(days=i),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("95"),
                close=Decimal("100" if i == 0 else "105"),
                volume=100,
            )
            for i in range(3)
        ]
        for c in candles:
            atr.update(c)
        assert atr.is_ready
        # first TR = 15 (high-low)
        # subsequent TR = max(15, |110-105|=5, |95-105|=10) = 15
        # average = 15
        assert atr.value == Decimal("15")

    def test_reset(self) -> None:
        atr = ATRCalculator(period=3)
        atr.update(
            Candle(
                symbol="X",
                timestamp=datetime(2024, 1, 1, tzinfo=UTC),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("95"),
                close=Decimal("105"),
                volume=100,
            )
        )
        atr.reset()
        assert atr.value == Decimal("0")

    def test_invalid_period_raises(self) -> None:
        with pytest.raises(ValueError):
            ATRCalculator(period=0)


class TestVolumeProfile:
    def test_empty_poc(self) -> None:
        vp = VolumeProfile()
        assert vp.poc == Decimal("0")
        assert vp.value_area == (Decimal("0"), Decimal("0"))

    def test_poc_highest_volume_price(self) -> None:
        vp = VolumeProfile(price_bucket=Decimal("1"))
        vp.update(Decimal("100"), 50)
        vp.update(Decimal("101"), 200)
        vp.update(Decimal("102"), 100)
        assert vp.poc == Decimal("101")

    def test_value_area_70_pct(self) -> None:
        vp = VolumeProfile(value_pct=70, price_bucket=Decimal("1"))
        # Total = 1000. Need 700+ to define value area.
        vp.update(Decimal("100"), 100)
        vp.update(Decimal("101"), 600)  # POC
        vp.update(Decimal("102"), 300)
        # accumulate from POC: 600, then add 300 (right), then 100 (left) → 1000 ≥ 700
        lo, hi = vp.value_area
        assert lo <= Decimal("101") <= hi

    def test_reset(self) -> None:
        vp = VolumeProfile()
        vp.update(Decimal("100"), 50)
        vp.reset()
        assert vp.total_volume == 0

    def test_invalid_pct_raises(self) -> None:
        with pytest.raises(ValueError):
            VolumeProfile(value_pct=0)
        with pytest.raises(ValueError):
            VolumeProfile(value_pct=101)


class TestAnalyticsIsolation:
    def test_analytics_does_not_import_adapters(self) -> None:
        from pathlib import Path

        analytics_dir = Path(__file__).parent.parent / "market" / "analytics"
        for fp in analytics_dir.glob("*.py"):
            if fp.name == "__init__.py":
                continue
            content = fp.read_text()
            for forbidden in (
                "brokers.adapters",
                "brokers.trading",
                "brokers.services",
                "brokers.infrastructure",
            ):
                assert forbidden not in content, f"{fp.name} imports {forbidden}"

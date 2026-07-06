"""Unit tests for the OrderFlowAnalyzer in ``brokers.market.analytics``."""

from __future__ import annotations

import threading
from decimal import Decimal
from types import SimpleNamespace

from inc_trade.domain.entities import Trade
from inc_trade.domain.enums import Side
from inc_trade.market.analytics.order_flow import (
    OrderFlowAnalyzer,
    OrderFlowMetrics,
)


def _trade(
    side: Side,
    qty: int,
    price: Decimal = Decimal("100"),
    trade_id: str = "T-1",
) -> Trade:
    """Build a well-formed Trade for tests."""
    return Trade(
        trade_id=trade_id,
        order_id="O-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=side,
        quantity=qty,
        price=price,
    )


class TestOrderFlowBasics:
    def test_empty_snapshot_returns_zeros(self) -> None:
        of = OrderFlowAnalyzer()
        m = of.snapshot()
        assert isinstance(m, OrderFlowMetrics)
        assert m.total_buy_volume == 0
        assert m.total_sell_volume == 0
        assert m.volume_delta == 0
        assert m.cumulative_delta == 0
        assert m.bar_delta == 0
        assert m.bar_buy_volume == 0
        assert m.bar_sell_volume == 0
        assert m.trade_count == 0
        assert m.bar_trade_count == 0
        assert m.large_trade_count == 0
        assert m.average_trade_size == Decimal("0")
        assert m.buy_sell_pressure == Decimal("0")
        assert m.last_trade_price is None

    def test_single_buy_updates_buy_volume(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, 100, Decimal("50.5")))
        m = of.snapshot()
        assert m.total_buy_volume == 100
        assert m.total_sell_volume == 0
        assert m.volume_delta == 100
        assert m.cumulative_delta == 100
        assert m.bar_delta == 100
        assert m.bar_buy_volume == 100
        assert m.bar_sell_volume == 0
        assert m.trade_count == 1
        assert m.bar_trade_count == 1
        assert m.last_trade_price == Decimal("50.5")

    def test_single_sell_updates_sell_volume(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.SELL, 75, Decimal("200")))
        m = of.snapshot()
        assert m.total_buy_volume == 0
        assert m.total_sell_volume == 75
        assert m.volume_delta == -75
        assert m.cumulative_delta == -75
        assert m.bar_delta == -75
        assert m.bar_buy_volume == 0
        assert m.bar_sell_volume == 75
        assert m.last_trade_price == Decimal("200")

    def test_multiple_trades_compute_cumulative_delta(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, 100, Decimal("100"), trade_id="T1"))
        of.update(_trade(Side.SELL, 30, Decimal("101"), trade_id="T2"))
        of.update(_trade(Side.BUY, 50, Decimal("102"), trade_id="T3"))
        of.update(_trade(Side.SELL, 80, Decimal("103"), trade_id="T4"))
        of.update(_trade(Side.BUY, 25, Decimal("104"), trade_id="T5"))
        m = of.snapshot()
        # buy 100+50+25 = 175, sell 30+80 = 110, delta = 65
        assert m.total_buy_volume == 175
        assert m.total_sell_volume == 110
        assert m.volume_delta == 65
        assert m.cumulative_delta == 65
        assert m.trade_count == 5

    def test_last_trade_price_updated(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, 10, Decimal("100.5")))
        of.update(_trade(Side.SELL, 5, Decimal("99.75")))
        m = of.snapshot()
        assert m.last_trade_price == Decimal("99.75")


class TestResetBar:
    def test_reset_bar_clears_bar_keeps_cumulative(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, 200, Decimal("100")))
        of.update(_trade(Side.SELL, 50, Decimal("101")))

        # Pre-reset: bar counts trades.
        m = of.snapshot()
        assert m.trade_count == 2
        assert m.bar_trade_count == 2
        assert m.bar_buy_volume == 200
        assert m.bar_sell_volume == 50
        assert m.bar_delta == 150

        # Reset bar.
        of.reset_bar()
        m = of.snapshot()
        # Cumulative preserved.
        assert m.total_buy_volume == 200
        assert m.total_sell_volume == 50
        assert m.cumulative_delta == 150
        assert m.trade_count == 2
        assert m.large_trade_count == 0
        # Bar counters cleared.
        assert m.bar_buy_volume == 0
        assert m.bar_sell_volume == 0
        assert m.bar_delta == 0
        assert m.bar_trade_count == 0

    def test_reset_bar_twice_idempotent(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, 100))
        of.reset_bar()
        of.reset_bar()
        m = of.snapshot()
        assert m.bar_trade_count == 0
        assert m.total_buy_volume == 100  # cumulative untouched

    def test_reset_clears_everything(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, 100, Decimal("100")))
        of.update(_trade(Side.SELL, 50, Decimal("101")))
        of.reset()
        m = of.snapshot()
        assert m.total_buy_volume == 0
        assert m.total_sell_volume == 0
        assert m.trade_count == 0
        assert m.large_trade_count == 0
        assert m.last_trade_price is None


class TestLargeTradeCounting:
    def test_large_trade_counted_at_threshold(self) -> None:
        of = OrderFlowAnalyzer(large_trade_threshold=1000)
        of.update(_trade(Side.BUY, 999, Decimal("100"), trade_id="T1"))
        m = of.snapshot()
        assert m.large_trade_count == 0

        of.update(_trade(Side.BUY, 1000, Decimal("100"), trade_id="T2"))
        m = of.snapshot()
        assert m.large_trade_count == 1  # exactly threshold counts

    def test_large_trade_above_threshold(self) -> None:
        of = OrderFlowAnalyzer(large_trade_threshold=500)
        of.update(_trade(Side.BUY, 2500, Decimal("100"), trade_id="T1"))
        of.update(_trade(Side.SELL, 100, Decimal("100"), trade_id="T2"))
        of.update(_trade(Side.SELL, 600, Decimal("100"), trade_id="T3"))
        m = of.snapshot()
        assert m.large_trade_count == 2

    def test_zero_threshold_counts_every_trade(self) -> None:
        of = OrderFlowAnalyzer(large_trade_threshold=0)
        of.update(_trade(Side.BUY, 1))
        of.update(_trade(Side.SELL, 1))
        m = of.snapshot()
        assert m.large_trade_count == 2

    def test_invalid_threshold_raises(self) -> None:
        import pytest

        with pytest.raises(ValueError):
            OrderFlowAnalyzer(large_trade_threshold=-1)


class TestPressureRatio:
    def test_pressure_ratio_buy_over_sell(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, 300))
        of.update(_trade(Side.SELL, 100))
        m = of.snapshot()
        assert m.buy_sell_pressure == Decimal("3")

    def test_pressure_ratio_fractional(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, 250))
        of.update(_trade(Side.SELL, 1000))
        m = of.snapshot()
        assert m.buy_sell_pressure == Decimal("250") / Decimal("1000")
        assert m.buy_sell_pressure == Decimal("0.25")

    def test_pressure_zero_when_no_sells(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, 1000))
        m = of.snapshot()
        # No sells → can't compute meaningful ratio, return 0.
        assert m.buy_sell_pressure == Decimal("0")

    def test_pressure_one_when_equal(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, 500))
        of.update(_trade(Side.SELL, 500))
        m = of.snapshot()
        assert m.buy_sell_pressure == Decimal("1")


class TestAverageTradeSize:
    def test_average_size_simple(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, 100))
        of.update(_trade(Side.SELL, 200))
        of.update(_trade(Side.BUY, 300))
        m = of.snapshot()
        # avg = 600 / 3 = 200
        assert m.average_trade_size == Decimal("200")

    def test_average_size_decimal_precision(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, 100))
        of.update(_trade(Side.SELL, 200))
        m = of.snapshot()
        # avg = 300 / 2 = 150
        assert m.average_trade_size == Decimal("150")

    def test_average_size_zero_trades(self) -> None:
        of = OrderFlowAnalyzer()
        m = of.snapshot()
        assert m.average_trade_size == Decimal("0")


class TestDefensiveUpdates:
    def test_update_with_none_side_does_not_raise(self) -> None:
        of = OrderFlowAnalyzer()
        bad = Trade(
            trade_id="T-BAD",
            order_id="O-1",
            symbol="X",
            exchange="NSE",
            side=None,  # type: ignore[arg-type]
            quantity=100,
            price=Decimal("100"),
        )
        # Must not raise.
        of.update(bad)
        m = of.snapshot()
        assert m.trade_count == 0
        assert m.total_buy_volume == 0
        assert m.total_sell_volume == 0

    def test_update_with_zero_quantity_dropped(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, 0))
        m = of.snapshot()
        assert m.trade_count == 0
        assert m.total_buy_volume == 0

    def test_update_with_negative_quantity_dropped(self) -> None:
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, -10))
        m = of.snapshot()
        assert m.trade_count == 0

    def test_update_with_missing_quantity_attr_dropped(self) -> None:
        """Duck-typed trade without ``quantity`` attribute must be ignored."""
        of = OrderFlowAnalyzer()
        bad = SimpleNamespace(
            trade_id="T-BAD",
            order_id="O-1",
            symbol="X",
            exchange="NSE",
            side=Side.BUY,
            price=Decimal("100"),
            # quantity intentionally missing
        )
        of.update(bad)  # type: ignore[arg-type]
        m = of.snapshot()
        assert m.trade_count == 0

    def test_update_with_missing_price_attr_dropped(self) -> None:
        of = OrderFlowAnalyzer()
        bad = SimpleNamespace(
            trade_id="T-BAD",
            order_id="O-1",
            symbol="X",
            exchange="NSE",
            side=Side.BUY,
            quantity=100,
            # price missing
        )
        of.update(bad)  # type: ignore[arg-type]
        m = of.snapshot()
        assert m.trade_count == 0

    def test_update_with_none_price_dropped(self) -> None:
        of = OrderFlowAnalyzer()
        bad = Trade(
            trade_id="T-BAD",
            order_id="O-1",
            symbol="X",
            exchange="NSE",
            side=Side.BUY,
            quantity=100,
            price=None,  # type: ignore[arg-type]
        )
        of.update(bad)
        m = of.snapshot()
        assert m.trade_count == 0

    def test_update_with_unknown_side_dropped(self) -> None:
        of = OrderFlowAnalyzer()
        bad = SimpleNamespace(
            trade_id="T-BAD",
            order_id="O-1",
            symbol="X",
            exchange="NSE",
            side="HOLD",  # not BUY/SELL
            quantity=100,
            price=Decimal("100"),
        )
        of.update(bad)  # type: ignore[arg-type]
        m = of.snapshot()
        assert m.trade_count == 0

    def test_update_with_zero_price_accepted(self) -> None:
        """Zero price is valid (e.g. option expiry, special auctions)."""
        of = OrderFlowAnalyzer()
        of.update(_trade(Side.BUY, 100, Decimal("0")))
        m = of.snapshot()
        assert m.trade_count == 1
        assert m.last_trade_price == Decimal("0")

    def test_bad_trade_does_not_corrupt_state(self) -> None:
        """After a bad trade, subsequent valid trades still update correctly."""
        of = OrderFlowAnalyzer()
        # Bad trade first
        bad = SimpleNamespace(
            trade_id="T-BAD",
            order_id="O-1",
            symbol="X",
            exchange="NSE",
            side=Side.BUY,
            quantity=999,  # huge, but missing price
        )
        of.update(bad)  # type: ignore[arg-type]
        # Now a good trade
        of.update(_trade(Side.SELL, 50))
        m = of.snapshot()
        assert m.trade_count == 1
        assert m.total_sell_volume == 50
        assert m.total_buy_volume == 0


class TestThreadSafety:
    def test_concurrent_updates_no_lost_trades(self) -> None:
        """10 threads, 1000 trades each — every trade must be counted.

        The lock must serialize updates so the final trade_count is
        exactly ``10 * 1000 = 10000``.
        """
        of = OrderFlowAnalyzer()
        n_threads = 10
        trades_per_thread = 1000
        errors: list[BaseException] = []

        def worker(thread_idx: int) -> None:
            try:
                for i in range(trades_per_thread):
                    # Alternate sides to exercise both branches.
                    side = Side.BUY if (i % 2 == 0) else Side.SELL
                    of.update(
                        _trade(
                            side,
                            qty=10,
                            price=Decimal("100"),
                            trade_id=f"T-{thread_idx}-{i}",
                        )
                    )
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        m = of.snapshot()
        assert m.trade_count == n_threads * trades_per_thread
        # Even count: equal buy/sell.
        assert m.total_buy_volume == n_threads * trades_per_thread // 2 * 10
        assert m.total_sell_volume == n_threads * trades_per_thread // 2 * 10
        assert m.volume_delta == 0
        assert m.large_trade_count == 0  # qty=10, threshold=1000

    def test_concurrent_updates_with_large_trades(self) -> None:
        """Verify large_trade_count is also atomic under contention."""
        of = OrderFlowAnalyzer(large_trade_threshold=10)
        n_threads = 5
        trades_per_thread = 200
        threads = []
        for i in range(n_threads):
            threads.append(
                threading.Thread(
                    target=lambda idx=i: [
                        of.update(
                            _trade(
                                Side.BUY,
                                qty=50,
                                price=Decimal("100"),
                                trade_id=f"T-{idx}-{j}",
                            )
                        )
                        for j in range(trades_per_thread)
                    ]
                )
            )
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        m = of.snapshot()
        assert m.trade_count == n_threads * trades_per_thread
        assert m.large_trade_count == n_threads * trades_per_thread


class TestExports:
    def test_exported_from_analytics_package(self) -> None:
        from inc_trade.market.analytics import OrderFlowAnalyzer, OrderFlowMetrics

        assert OrderFlowAnalyzer is not None
        assert OrderFlowMetrics is not None

    def test_metrics_is_frozen(self) -> None:
        """``OrderFlowMetrics`` must be immutable (frozen dataclass)."""
        import dataclasses

        m = OrderFlowMetrics(
            total_buy_volume=0,
            total_sell_volume=0,
            volume_delta=0,
            cumulative_delta=0,
            bar_delta=0,
            bar_buy_volume=0,
            bar_sell_volume=0,
            trade_count=0,
            bar_trade_count=0,
            large_trade_count=0,
            average_trade_size=Decimal("0"),
            buy_sell_pressure=Decimal("0"),
            last_trade_price=None,
        )
        assert dataclasses.is_dataclass(m)
        # Frozen check: mutation should raise.
        import pytest

        with pytest.raises(dataclasses.FrozenInstanceError):
            m.total_buy_volume = 1  # type: ignore[misc]

    def test_analytics_module_isolated_from_adapters(self) -> None:
        """Order flow must not import forbidden boundary layers."""
        from pathlib import Path

        fp = (
            Path(__file__).parent.parent.parent.parent
            / "inc_trade"
            / "market"
            / "analytics"
            / "order_flow.py"
        )
        content = fp.read_text()
        for forbidden in (
            "brokers.adapters",
            "brokers.trading",
            "brokers.services",
            "brokers.infrastructure",
        ):
            assert forbidden not in content, f"order_flow.py imports {forbidden}"

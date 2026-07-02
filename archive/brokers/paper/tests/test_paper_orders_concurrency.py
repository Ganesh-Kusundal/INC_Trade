"""Concurrency tests for PaperOrders."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

from brokers.paper.paper_market_data import PaperMarketData
from brokers.paper.paper_orders import PaperOrders
from domain import OrderStatus, Side


class TestPaperOrdersConcurrency:
    def test_concurrent_place_order_generates_unique_ids(self):
        md = PaperMarketData()
        orders = PaperOrders(md, {})

        def place():
            return orders.place_order("RELIANCE", "NSE", Side.BUY, 1)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(place) for _ in range(100)]
            results = [f.result() for f in as_completed(futures)]

        ids = [o.order_id for o in results]
        assert len(ids) == len(set(ids))
        assert all(o.status == OrderStatus.FILLED for o in results)

    def test_concurrent_place_order_updates_positions_atomically(self):
        md = PaperMarketData()
        orders = PaperOrders(md, {})

        def place():
            return orders.place_order("RELIANCE", "NSE", Side.BUY, 1)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(place) for _ in range(100)]
            for f in as_completed(futures):
                f.result()

        positions = orders.get_positions()
        assert len(positions) == 1
        pos = positions[0]
        assert pos.symbol == "RELIANCE"
        assert pos.exchange == "NSE"
        assert pos.quantity == 100
        assert pos.avg_price > Decimal("0")

    def test_position_copy_on_write_does_not_mutate_original(self):
        md = PaperMarketData()
        orders = PaperOrders(md, {})
        orders.place_order(
            "RELIANCE", "NSE", Side.BUY, 10, price=Decimal("100"), order_type="LIMIT"
        )

        first = orders.get_positions()[0]
        assert first.quantity == 10
        orders.place_order(
            "RELIANCE", "NSE", Side.BUY, 10, price=Decimal("120"), order_type="LIMIT"
        )
        second = orders.get_positions()[0]

        assert first is not second
        assert first.quantity == 10
        assert first.avg_price == Decimal("100")
        assert second.quantity == 20
        assert second.avg_price == Decimal("110")

    def test_cancel_order_replaces_immutable_order(self):
        md = PaperMarketData()
        orders = PaperOrders(md, {})
        o = orders.place_order(
            "RELIANCE", "NSE", Side.BUY, 10, price=Decimal("100"), order_type="LIMIT"
        )

        # Place an open order manually so cancellation has something to do.
        open_order = o.with_status(OrderStatus.OPEN)
        orders._orders = [open_order]
        assert orders.cancel_order(open_order.order_id) is True

        cancelled = orders.get_orderbook()[0]
        assert cancelled is not open_order
        assert cancelled.status == OrderStatus.CANCELLED

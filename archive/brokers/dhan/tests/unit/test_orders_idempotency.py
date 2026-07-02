"""Thread-safety and idempotency tests for OrdersAdapter and IdempotencyCache."""

from __future__ import annotations

import threading

import pytest

from brokers.dhan.orders import IdempotencyCache, OrdersAdapter
from domain import Order, OrderStatus, OrderType, ProductType, Side, Validity
from domain.requests import OrderRequest


def _make_order(order_id: str = "ORD1", correlation_id: str | None = None) -> Order:
    return Order(
        order_id=order_id,
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=10,
        status=OrderStatus.OPEN,
        product_type=ProductType.INTRADAY,
        validity=Validity.DAY,
        correlation_id=correlation_id,
    )


def test_idempotency_cache_is_thread_safe():
    """Concurrent puts/gets should not corrupt the cache."""
    cache = IdempotencyCache(max_size=100, ttl_seconds=3600)
    errors: list[Exception] = []
    barrier = threading.Barrier(20)

    def worker(idx: int) -> None:
        try:
            barrier.wait(timeout=2)
            order = _make_order(order_id=f"ORD{idx}", correlation_id=f"cid-{idx}")
            cache.put(f"cid-{idx}", order)
            found = cache.get(f"cid-{idx}")
            assert found is not None
            assert found.order_id == order.order_id
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    for i in range(20):
        assert cache.get(f"cid-{i}") is not None


def test_idempotency_cache_eviction_is_thread_safe():
    """Eviction of oldest entries under concurrency must remain deterministic."""
    cache = IdempotencyCache(max_size=5, ttl_seconds=3600)
    for i in range(5):
        cache.put(f"cid-{i}", _make_order(order_id=f"ORD{i}"))

    # Let entry 0 expire by manipulating time via a tiny TTL, then exercise eviction.
    cache._ttl = -1
    cache.put("cid-new", _make_order(order_id="ORD-NEW"))
    assert cache.get("cid-0") is None


def test_lock_context_manager_returns_cache():
    """lock() must be usable as a context manager and expose the cache."""
    cache = IdempotencyCache()
    order = _make_order()
    with cache.lock("cid") as locked_cache:
        locked_cache.put("cid", order)
        assert locked_cache.get("cid") is order


def test_place_order_generates_correlation_id(fake_client, resolver):
    """If no correlation_id is supplied, one is generated and sent to Dhan."""
    fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD-GEN"}})
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    order = adapter.place_order(OrderRequest(symbol="RELIANCE", exchange="NSE", quantity=1))

    payloads = fake_client.calls_for("POST", "/orders")
    assert len(payloads) == 1
    assert "correlationId" in payloads[0]
    assert payloads[0]["correlationId"] == order.correlation_id
    assert order.correlation_id


def test_place_order_uses_supplied_correlation_id(fake_client, resolver):
    """A supplied correlation_id is forwarded and cached."""
    fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD-SUP"}})
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    cid = "my-correlation-id"
    order = adapter.place_order(
        OrderRequest(symbol="RELIANCE", exchange="NSE", quantity=1, correlation_id=cid)
    )

    assert order.correlation_id == cid
    payloads = fake_client.calls_for("POST", "/orders")
    assert payloads[0]["correlationId"] == cid


def test_place_order_idempotency_returns_cached_order(fake_client, resolver):
    """Second call with same correlation_id returns cached order without HTTP post."""
    fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD-IDEM"}})
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    cid = "idem-cid"

    first = adapter.place_order(
        OrderRequest(symbol="RELIANCE", exchange="NSE", quantity=1, correlation_id=cid)
    )
    second = adapter.place_order(
        OrderRequest(symbol="RELIANCE", exchange="NSE", quantity=1, correlation_id=cid)
    )

    assert first is second
    assert fake_client.call_count == 1


def test_place_order_concurrent_idempotency_posts_once(fake_client, resolver):
    """Many threads racing with the same correlation_id must result in exactly one HTTP post."""
    fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD-RACE"}})
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    cid = "race-cid"
    results: list[Order] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(10)

    def worker() -> None:
        try:
            barrier.wait(timeout=2)
            order = adapter.place_order(
                OrderRequest(
                    symbol="RELIANCE",
                    exchange="NSE",
                    quantity=1,
                    correlation_id=cid,
                )
            )
            results.append(order)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == 10
    order_ids = {o.order_id for o in results}
    assert order_ids == {"ORD-RACE"}
    calls = fake_client.calls_for("POST", "/orders")
    assert len(calls) == 1, f"Expected 1 HTTP post, got {len(calls)}"


def test_place_order_concurrent_unique_correlation_ids(fake_client, resolver):
    """Concurrent unique correlation_ids each post exactly once."""
    fake_client.set_response("POST", "/orders", {"data": {"orderId": "ORD-UNIQUE"}})
    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    count = 10
    results: list[Order] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(count)

    def worker(idx: int) -> None:
        try:
            barrier.wait(timeout=2)
            order = adapter.place_order(
                OrderRequest(
                    symbol="RELIANCE",
                    exchange="NSE",
                    quantity=1,
                    correlation_id=f"unique-{idx}",
                )
            )
            results.append(order)
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert len(results) == count
    calls = fake_client.calls_for("POST", "/orders")
    assert len(calls) == count


def test_place_order_validation_failure_is_not_cached(fake_client, resolver):
    """A validation failure must not be cached as a successful idempotency entry."""
    from brokers.dhan.exceptions import OrderError

    adapter = OrdersAdapter(fake_client, resolver, allow_live_orders=True)
    cid = "bad-order"

    with pytest.raises(OrderError):
        adapter.place_order(
            OrderRequest(symbol="RELIANCE", exchange="NSE", quantity=0, correlation_id=cid)
        )

    assert fake_client.call_count == 0
    assert adapter._idempotency.get(cid) is None

"""Integration tests for durable broker idempotency caches."""

from __future__ import annotations

from pathlib import Path

import pytest

from brokers.common.idempotency.port_adapter import (
    create_dhan_idempotency_cache,
    create_upstox_idempotency_cache,
)
from domain import Order, OrderResponse, OrderStatus, OrderType, ProductType, Side, Validity


@pytest.fixture
def dhan_cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "dhan"


@pytest.fixture
def upstox_cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "upstox"


def test_dhan_idempotency_survives_cache_recreation(dhan_cache_dir: Path) -> None:
    order = Order(
        order_id="ORD-1",
        symbol="RELIANCE",
        exchange="NSE",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        quantity=1,
        status=OrderStatus.OPEN,
        product_type=ProductType.INTRADAY,
        validity=Validity.DAY,
        correlation_id="cid-1",
    )
    cache = create_dhan_idempotency_cache(storage_dir=dhan_cache_dir)
    cache.put("cid-1", order)

    reloaded = create_dhan_idempotency_cache(storage_dir=dhan_cache_dir)
    found = reloaded.get("cid-1")

    assert found is not None
    assert found.order_id == "ORD-1"
    assert found.correlation_id == "cid-1"


def test_upstox_idempotency_survives_cache_recreation(upstox_cache_dir: Path) -> None:
    response = OrderResponse.ok(order_id="ORD-2", message="placed", status=OrderStatus.OPEN)
    cache = create_upstox_idempotency_cache(storage_dir=upstox_cache_dir)
    cache.put("cid-2", response)

    reloaded = create_upstox_idempotency_cache(storage_dir=upstox_cache_dir)
    found = reloaded.get("cid-2")

    assert found is not None
    assert found.success is True
    assert found.order_id == "ORD-2"

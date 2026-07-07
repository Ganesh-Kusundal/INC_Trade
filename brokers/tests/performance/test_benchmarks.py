"""Benchmark tests — measure hot-path latency with PaperProvider.

Uses ``pytest-benchmark`` to record and compare execution times for
critical code paths.  All benchmarks use the Paper provider (zero
network, deterministic) so results are reproducible across CI runs.

All benchmark functions are **synchronous** (not ``@pytest.mark.asyncio``)
because they use ``asyncio.run()`` to drive async provider methods in a
fresh event loop.  This avoids event-loop nesting conflicts.

Run::

    pytest brokers/tests/performance/ --benchmark-only
    pytest brokers/tests/performance/ --benchmark-autosave
    pytest brokers/tests/performance/ --benchmark-compare

Hot paths measured:
- Quote / LTP / Depth retrieval (market data round-trip)
- Historical data retrieval
- Order placement (execution round-trip)
- Idempotency cache get/put (cache hit rate)
- Provider connect/disconnect lifecycle
- Instrument resolution
"""

from __future__ import annotations

import asyncio
from datetime import date
from decimal import Decimal

import pytest

from brokers.common.idempotency import MemoryIdempotencyCache
from brokers.domain.enums import Exchange, OrderType, ProductType, Side
from brokers.domain.instrument import Instrument
from brokers.domain.requests import OrderRequest
from brokers.paper.paper_provider import PaperProvider


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def provider() -> PaperProvider:
    """Fresh PaperProvider with default seeded prices."""
    return PaperProvider()


@pytest.fixture
def reliance(provider: PaperProvider) -> Instrument:
    """Pre-resolved RELIANCE instrument."""
    return Instrument(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        provider=provider,  # type: ignore[arg-type]
        security_id="3456",
    )


@pytest.fixture
def cache() -> MemoryIdempotencyCache[dict]:
    """Fresh MemoryIdempotencyCache."""
    return MemoryIdempotencyCache[dict](default_ttl=3600)


# ── Helper ──────────────────────────────────────────────────────────────────


def _run(coro):
    """Run a coroutine synchronously via asyncio.run()."""
    return asyncio.run(coro)


# ── Market data benchmarks ──────────────────────────────────────────────────


def test_bench_get_quote(
    benchmark, provider: PaperProvider, reliance: Instrument
) -> None:
    """Measure quote retrieval latency."""
    result = benchmark(lambda: _run(provider.get_quote(reliance)))
    assert result.ltp > 0


def test_bench_get_ltp(
    benchmark, provider: PaperProvider, reliance: Instrument
) -> None:
    """Measure LTP lookup latency."""
    result = benchmark(lambda: _run(provider.get_ltp(reliance)))
    assert result > 0


def test_bench_get_depth(
    benchmark, provider: PaperProvider, reliance: Instrument
) -> None:
    """Measure market depth retrieval latency."""
    result = benchmark(lambda: _run(provider.get_depth(reliance)))
    assert len(result.bids) == 5
    assert len(result.asks) == 5


def test_bench_get_history(
    benchmark, provider: PaperProvider, reliance: Instrument
) -> None:
    """Measure historical data retrieval latency (most expensive market-data op)."""
    result = benchmark(
        lambda: _run(provider.get_history(
            reliance, timeframe="1D", bars=10,
            from_date=date(2026, 1, 1), to_date=date(2026, 1, 10),
        ))
    )
    assert len(result.bars) == 10


# ── Execution benchmarks ────────────────────────────────────────────────────


def test_bench_place_order_market(
    benchmark, provider: PaperProvider
) -> None:
    """Measure market order placement round-trip latency."""
    request = OrderRequest(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        side=Side.BUY,
        quantity=10,
        order_type=OrderType.MARKET,
        product_type=ProductType.CNC,
    )

    async def _place():
        return await provider.place_order(request)

    result = benchmark(lambda: _run(_place()))
    assert result.success is True


def test_bench_place_order_limit(
    benchmark, provider: PaperProvider
) -> None:
    """Measure limit order placement round-trip latency."""
    request = OrderRequest(
        symbol="RELIANCE",
        exchange=Exchange.NSE,
        side=Side.SELL,
        quantity=5,
        order_type=OrderType.LIMIT,
        product_type=ProductType.CNC,
        price=Decimal("2600.00"),
    )

    async def _place():
        return await provider.place_order(request)

    result = benchmark(lambda: _run(_place()))
    assert result.success is True


def test_bench_place_and_get_positions(
    benchmark, provider: PaperProvider
) -> None:
    """Measure order placement + position query round-trip."""

    async def _roundtrip() -> None:
        request = OrderRequest(
            symbol="RELIANCE", exchange=Exchange.NSE,
            side=Side.BUY, quantity=100, order_type=OrderType.MARKET,
            product_type=ProductType.CNC,
        )
        await provider.place_order(request)
        await provider.get_positions()

    benchmark(lambda: _run(_roundtrip()))


# ── Cache benchmarks ────────────────────────────────────────────────────────


def test_bench_cache_put(benchmark, cache: MemoryIdempotencyCache[dict]) -> None:
    """Measure cache put_if_absent latency (new key)."""
    counter = 0

    def _put_new() -> bool:
        nonlocal counter
        counter += 1
        return cache.put_if_absent(f"bench-key-{counter}", {"v": 1})

    result = benchmark(_put_new)
    assert result is True


def test_bench_cache_put_duplicate(
    benchmark, cache: MemoryIdempotencyCache[dict]
) -> None:
    """Measure cache put_if_absent latency (duplicate key)."""
    cache.put_if_absent("dup-key", {"v": 1})
    result = benchmark(lambda: cache.put_if_absent("dup-key", {"v": 2}))
    assert result is False


def test_bench_cache_get_hit(
    benchmark, cache: MemoryIdempotencyCache[dict]
) -> None:
    """Measure cache get latency (hit)."""
    cache.put_if_absent("hit-key", {"v": 1})
    result = benchmark(lambda: cache.get("hit-key"))
    assert result == {"v": 1}


def test_bench_cache_get_miss(
    benchmark, cache: MemoryIdempotencyCache[dict]
) -> None:
    """Measure cache get latency (miss)."""
    result = benchmark(lambda: cache.get("miss-key"))
    assert result is None


def test_bench_cache_contains_true(
    benchmark, cache: MemoryIdempotencyCache[dict]
) -> None:
    """Measure cache __contains__ latency (present key)."""
    cache.put_if_absent("in-key", {"v": 1})
    result = benchmark(lambda: "in-key" in cache)
    assert result is True


def test_bench_cache_contains_false(
    benchmark, cache: MemoryIdempotencyCache[dict]
) -> None:
    """Measure cache __contains__ latency (absent key)."""
    result = benchmark(lambda: "not-in-key" in cache)
    assert result is False


# ── Lifecycle benchmarks ────────────────────────────────────────────────────


def test_bench_connect_disconnect(benchmark, provider: PaperProvider) -> None:
    """Measure connect + disconnect latency."""

    async def _lifecycle() -> None:
        await provider.connect()
        await provider.disconnect()

    benchmark(lambda: _run(_lifecycle()))


# ── Instrument benchmarks ───────────────────────────────────────────────────


def test_bench_instrument_resolution(
    benchmark, provider: PaperProvider
) -> None:
    """Measure instrument resolution latency."""
    result = benchmark(
        lambda: _run(provider.resolve_instrument("RELIANCE", "NSE"))
    )
    assert result.symbol == "RELIANCE"


def test_bench_search_instruments(
    benchmark, provider: PaperProvider
) -> None:
    """Measure instrument search latency."""
    result = benchmark(lambda: _run(provider.search_instruments("REL")))
    assert len(result) > 0


# ── Derivative benchmarks ───────────────────────────────────────────────────


def test_bench_option_chain(
    benchmark, provider: PaperProvider, reliance: Instrument
) -> None:
    """Measure option chain retrieval latency."""
    result = benchmark(lambda: _run(provider.get_option_chain(reliance)))
    assert result.spot is not None


def test_bench_future_chain(
    benchmark, provider: PaperProvider, reliance: Instrument
) -> None:
    """Measure future chain retrieval latency."""
    result = benchmark(lambda: _run(provider.get_future_chain(reliance)))
    assert len(result.contracts) == 2


# ── Capabilities benchmark ──────────────────────────────────────────────────


def test_bench_capabilities_check(benchmark, provider: PaperProvider) -> None:
    """Measure capabilities.supports() check latency."""
    caps = provider.capabilities
    result = benchmark(lambda: caps.supports("MARKET_DATA"))
    assert result is True


# ── Provider identity benchmark ─────────────────────────────────────────────


def test_bench_broker_id(benchmark, provider: PaperProvider) -> None:
    """Measure broker_id property access latency."""
    result = benchmark(lambda: provider.broker_id)
    assert result == "paper"


__all__ = [
    "test_bench_get_quote",
    "test_bench_get_ltp",
    "test_bench_get_depth",
    "test_bench_get_history",
    "test_bench_place_order_market",
    "test_bench_place_order_limit",
    "test_bench_place_and_get_positions",
    "test_bench_cache_put",
    "test_bench_cache_put_duplicate",
    "test_bench_cache_get_hit",
    "test_bench_cache_get_miss",
    "test_bench_cache_contains_true",
    "test_bench_cache_contains_false",
    "test_bench_connect_disconnect",
    "test_bench_instrument_resolution",
    "test_bench_search_instruments",
    "test_bench_option_chain",
    "test_bench_future_chain",
    "test_bench_capabilities_check",
    "test_bench_broker_id",
]

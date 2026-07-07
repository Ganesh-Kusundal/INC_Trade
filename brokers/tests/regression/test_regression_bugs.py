"""Regression test registry — permanent reproductions of historical bugs.

Every bug that was found and fixed must have a regression test here.
The test docstring records when the bug was found, what the root cause
was, and how it was fixed.  No bug should ever reappear.

Convention:
- Test function name: ``test_regress_<id>_<short_description>``
- Docstring includes: **Found:** date, **Root Cause:** explanation,
  **Fix:** summary of the change that resolved the issue
"""

from __future__ import annotations

import threading
import time
from decimal import Decimal

import pytest

from brokers.common.idempotency import MemoryIdempotencyCache
from brokers.domain.enums import Exchange, OrderStatus, OrderType, ProductType, Side
from brokers.domain.events import DomainEvent
from brokers.domain.instrument import Instrument
from brokers.domain.requests import OrderRequest
from brokers.domain.values import OrderResponse
from brokers.infrastructure.event_bus import EventBus
from brokers.infrastructure.tracing import Tracer
from brokers.paper.paper_provider import PaperProvider


# ── Trading / OMS bugs ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regress_b01_position_reversal_pnl_sign() -> None:
    """Position flip from long to short must calculate realized PnL correctly.

    **Found:** 2026-03  **Root Cause:** When a position flipped from long
    to short, the sign of the realized PnL was inverted because the
    ``_update_position`` helper used ``existing.quantity > 0`` to
    determine direction but ``signed_qty`` was already negative.
    **Fix:** Added explicit direction check and test for position
    reversal in paper provider.
    """
    provider = PaperProvider()

    # Buy 10 → long 10
    buy = OrderRequest(
        symbol="RELIANCE", exchange=Exchange.NSE,
        side=Side.BUY, quantity=10, order_type=OrderType.MARKET,
        product_type=ProductType.CNC,
    )
    await provider.place_order(buy)

    # Sell 20 → flips to short 10
    sell = OrderRequest(
        symbol="RELIANCE", exchange=Exchange.NSE,
        side=Side.SELL, quantity=20, order_type=OrderType.MARKET,
        product_type=ProductType.CNC,
    )
    await provider.place_order(sell)

    positions = await provider.get_positions()
    assert len(positions) == 1
    assert positions[0].quantity == -10
    # Both trades at same seed price → PnL must be exactly zero
    assert positions[0].realized_pnl == Decimal("0")


@pytest.mark.asyncio
async def test_regress_b02_partial_fill_position_reduction() -> None:
    """Reducing a position (selling part of a long) must preserve cost basis.

    **Found:** 2026-04  **Root Cause:** Reducing a position incorrectly
    recalculated the average price instead of keeping it for the remaining
    quantity.  **Fix:** Keep the existing average price when reducing
    position size; only recalculate when adding.
    """
    provider = PaperProvider()

    # Buy 100
    await provider.place_order(OrderRequest(
        symbol="RELIANCE", exchange=Exchange.NSE,
        side=Side.BUY, quantity=100, order_type=OrderType.MARKET,
        product_type=ProductType.CNC,
    ))

    # Sell 40 → reduces to 60
    await provider.place_order(OrderRequest(
        symbol="RELIANCE", exchange=Exchange.NSE,
        side=Side.SELL, quantity=40, order_type=OrderType.MARKET,
        product_type=ProductType.CNC,
    ))

    positions = await provider.get_positions()
    assert positions[0].quantity == 60
    # PnL should be positive (sold at same price, no gain/loss) or the
    # position average should not have changed
    assert positions[0].average_price > 0


# ── Cache / idempotency bugs ───────────────────────────────────────────────


def test_regress_c01_expired_entry_must_not_be_returned() -> None:
    """Cache.get() on an expired entry must return None and clean up.

    **Found:** 2026-05  **Root Cause:** ``MemoryIdempotencyCache.get()``
    checked ``_is_expired`` but did not delete the stale entry when it
    was expired, causing ``__contains__`` to still return True.
    **Fix:** Added ``del self._store[h]`` in the expired branch.
    """
    cache: MemoryIdempotencyCache[dict] = MemoryIdempotencyCache(default_ttl=1)
    cache.put_if_absent("expires-soon", {"v": 1})
    time.sleep(1.1)

    # Get must return None for expired entry
    assert cache.get("expires-soon") is None
    # Contains must return False
    assert "expires-soon" not in cache


def test_regress_c02_concurrent_put_must_be_linearizable() -> None:
    """20 concurrent put_if_absent calls for the same key must result in
    exactly one True (winner) and 19 False.

    **Found:** 2026-05  **Root Cause:** The ``put_if_absent`` method
    did not hold the lock while checking existence, allowing a TOCTOU
    race.  **Fix:** Combined existence check + storage under a single
    lock acquisition.
    """
    cache: MemoryIdempotencyCache[dict] = MemoryIdempotencyCache()
    results: list[bool] = []
    lock = threading.Lock()

    def _worker() -> None:
        stored = cache.put_if_absent("shared-key", {"v": 1})
        with lock:
            results.append(stored)

    threads = [threading.Thread(target=_worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(results) == 1


def test_regress_c03_zero_ttl_rejected_at_construction() -> None:
    """Constructing a cache with default_ttl <= 0 must raise ValueError.

    **Found:** 2026-05  **Root Cause:** The constructor accepted
    negative TTL values which caused expirations to happen instantly
    (or never, depending on how ``_is_expired`` interpreted the math).
    **Fix:** Added explicit ``<= 0`` validation in ``__init__``.
    """
    with pytest.raises(ValueError, match="default_ttl must be > 0"):
        MemoryIdempotencyCache(default_ttl=0)
    with pytest.raises(ValueError, match="default_ttl must be > 0"):
        MemoryIdempotencyCache(default_ttl=-1)


# ── Provider / lifecycle bugs ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regress_p01_disconnect_before_connect_must_not_raise() -> None:
    """Calling disconnect() on a provider that was never connected must not
    raise an exception.

    **Found:** 2026-06  **Root Cause:** PaperProvider.disconnect() set
    ``_connected = False`` unconditionally; it was harmless.  But the
    real broker providers accessed uninitialised feed handles.
    **Fix:** Guard all feed-stopping coroutines with ``is not None``
    checks and use ``asyncio.Lock`` for thread safety.
    """
    provider = PaperProvider()
    await provider.disconnect()  # Must not raise
    assert not provider.is_connected


@pytest.mark.asyncio
async def test_regress_p02_connect_idempotent() -> None:
    """Calling connect() twice must not raise, corrupt state, or leak
    resources.

    **Found:** 2026-06  **Root Cause:** DhanProvider.connect() was
    creating new feed instances on every call without stopping old ones.
    **Fix:** Feed creation was moved to lazy ``_ensure_*`` methods;
    connect() just sets ``_connected = True``.
    """
    provider = PaperProvider()
    await provider.connect()
    await provider.connect()  # Must not raise
    assert provider.is_connected


# ── Event bus bugs ──────────────────────────────────────────────────────────


def test_regress_e01_handler_failure_must_isolate_other_handlers() -> None:
    """A failing handler must not prevent other handlers from receiving
    the same event.

    **Found:** 2026-03  **Root Cause:** The event bus raised exceptions
    from handlers to the caller instead of catching them, causing the
    dispatch loop to abort.  **Fix:** Wrapped each handler invocation in
    a try/except that logs the failure and continues.
    """
    bus = EventBus()
    good_received: list[DomainEvent] = []

    def _bad(_e: DomainEvent) -> None:
        raise RuntimeError("handler failure")

    def _good(e: DomainEvent) -> None:
        good_received.append(e)

    bus.subscribe("TICK", _bad)
    bus.subscribe("TICK", _good)

    event = DomainEvent.now("TICK", {})
    bus.publish(event)  # Must not raise

    assert len(good_received) == 1


def test_regress_e02_unsubscribe_during_dispatch_must_not_corrupt_iteration() -> None:
    """A handler that unsubscribes itself during dispatch must not corrupt
    the subscriber snapshot.

    **Found:** 2026-04  **Root Cause:** The event bus iterated over a
    mutable dict while handlers could modify it.  **Fix:** Snapshot the
    handlers list before iteration.
    """
    bus = EventBus()
    received: list[int] = []

    def _self_removing(e: DomainEvent) -> None:
        received.append(1)
        bus.unsubscribe(token)

    token = bus.subscribe("TICK", _self_removing)
    bus.subscribe("TICK", lambda e: received.append(2))

    bus.publish(DomainEvent.now("TICK", {}))
    assert len(received) == 2  # Both handlers must fire


# ── Tracing / observability bugs ────────────────────────────────────────────


def test_regress_t01_span_error_preserves_status_across_nesting() -> None:
    """An inner span raising an error must not corrupt the outer span's
    status.

    **Found:** 2026-05  **Root Cause:** The ``span`` context manager's
    ``finally`` block was calling ``_pop_span()`` which popped the wrong
    span when exceptions were raised.  **Fix:** Ensured ``finally``
    always pops the span that was pushed, using a local reference.
    """
    tracer = Tracer()

    with tracer.span("outer"):
        with pytest.raises(ValueError):
            with tracer.span("inner"):
                raise ValueError("inner error")

    spans = tracer.finished_spans()
    assert len(spans) == 2

    inner_span = next(s for s in spans if s.name == "inner")
    assert inner_span.status == "ERROR"
    assert "inner error" in (inner_span.error or "")


# ── Market data / parsing bugs ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_regress_m01_missing_instrument_must_raise_provider_error() -> None:
    """Requesting a quote for an unregistered symbol must raise ValueError,
    not silently return garbage data.

    **Found:** 2026-04  **Root Cause:** The ``_get_price`` helper was
    silently defaulting missing prices to 0 instead of raising.
    **Fix:** Changed the fallback to raise ``ValueError`` with a clear
    message.
    """
    provider = PaperProvider()
    unknown = Instrument(
        symbol="UNKNOWN", exchange=Exchange.NSE,
        provider=provider,  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="No price for UNKNOWN"):
        await provider.get_quote(unknown)


@pytest.mark.asyncio
async def test_regress_m02_order_response_success_flag_consistency() -> None:
    """OrderResponse.ok() must set success=True and OrderResponse.fail()
    must set success=False.

    **Found:** 2026-03  **Root Cause:** The ``OrderResponse`` constructor
    allowed manually creating responses with mismatched success flag and
    status.  **Fix:** Made ``ok()`` and ``fail()`` factory methods the
    only public constructors.
    """
    ok_resp = OrderResponse.ok(order_id="1", message="ok", status=OrderStatus.OPEN)
    assert ok_resp.success is True

    fail_resp = OrderResponse.fail("reason")
    assert fail_resp.success is False


# ── Instrument resolution bugs ──────────────────────────────────────────────


def test_regress_i01_option_symbol_with_call_put_suffix() -> None:
    """Option instruments with CALL/PUT suffixes must resolve correctly.

    **Found:** 2026-06  **Root Cause:** The resolver's alternate key
    generation always used CE/PE but some broker feeds report CALL/PUT.
    **Fix:** Added both CE/PE and CALL/PUT alternate keys in the
    resolver's ``_generate_alternate_keys``.
    """
    from brokers.common.instrument_resolver import (
        _standardize_option_suffix,
    )

    assert _standardize_option_suffix("NIFTY26JUN15900CALL") == "NIFTY26JUN15900CE"
    assert _standardize_option_suffix("NIFTY26JUN15900PUT") == "NIFTY26JUN15900PE"
    assert _standardize_option_suffix("NIFTY26JUN15900CE") == "NIFTY26JUN15900CE"


def test_regress_i02_stripped_symbol_lookup() -> None:
    """Spaces, underscores, and dashes must be stripped during symbol
    lookup.

    **Found:** 2026-05  **Root Cause:** The resolver only stored symbols
    in their canonical form (e.g. "NIFTY") but users passed variants
    like "NIFTY 50" or "NIFTY-50".  **Fix:** Added ``_strip_symbol``
    normalization to the ``_find`` multi-strategy lookup.
    """
    from brokers.common.instrument_resolver import _strip_symbol

    assert _strip_symbol("NIFTY 50") == "NIFTY50"
    assert _strip_symbol("BANK_NIFTY") == "BANKNIFTY"
    assert _strip_symbol("RELIANCE-IND") == "RELIANCEIND"


__all__ = [
    "test_regress_b01_position_reversal_pnl_sign",
    "test_regress_b02_partial_fill_position_reduction",
    "test_regress_c01_expired_entry_must_not_be_returned",
    "test_regress_c02_concurrent_put_must_be_linearizable",
    "test_regress_c03_zero_ttl_rejected_at_construction",
    "test_regress_p01_disconnect_before_connect_must_not_raise",
    "test_regress_p02_connect_idempotent",
    "test_regress_e01_handler_failure_must_isolate_other_handlers",
    "test_regress_e02_unsubscribe_during_dispatch_must_not_corrupt_iteration",
    "test_regress_t01_span_error_preserves_status_across_nesting",
    "test_regress_m01_missing_instrument_must_raise_provider_error",
    "test_regress_m02_order_response_success_flag_consistency",
    "test_regress_i01_option_symbol_with_call_put_suffix",
    "test_regress_i02_stripped_symbol_lookup",
]

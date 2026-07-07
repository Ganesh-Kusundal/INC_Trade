"""Lightweight soak test — sustained order/quote load on the Paper provider.

Opt-in via ``-m slow`` (or run directly).  The default non-live suite
ignores ``brokers/tests/performance`` so this never blocks CI.

Adapted from ``archive/refance-parallel-sdk/tests/test_soak.py``: instead of
hammering an EventBus/Cache, we drive a real (in-memory) provider through a
burst of buys + quote fetches and assert nothing crashes or deadlocks.
"""

from __future__ import annotations

import time

import pytest

from brokers.domain.enums import Exchange, OrderType, Side
from brokers.domain.instrument import Instrument
from brokers.domain.requests import OrderRequest
from brokers.domain.values import OrderResponse, Quote
from brokers.paper.paper_provider import PaperProvider

SOAK_DURATION_S = 0.5
SOAK_MAX_ITERATIONS = 500


@pytest.mark.slow
class TestPaperSoak:
    """Sustained load must complete without exceptions or deadlock."""

    @pytest.mark.asyncio
    async def test_sustained_orders_and_quotes(self) -> None:
        provider = PaperProvider()
        await provider.connect()

        inst = provider._instruments.get(
            "RELIANCE:NSE"
        ) or Instrument(symbol="RELIANCE", exchange=Exchange.NSE, provider=provider)

        start = time.monotonic()
        iterations = 0
        last_exception: BaseException | None = None

        try:
            while (
                time.monotonic() - start < SOAK_DURATION_S
                and iterations < SOAK_MAX_ITERATIONS
            ):
                resp = await provider.place_order(
                    OrderRequest(
                        symbol="RELIANCE",
                        exchange=Exchange.NSE,
                        side=Side.BUY,
                        quantity=1,
                        order_type=OrderType.MARKET,
                    )
                )
                assert isinstance(resp, OrderResponse)
                quote = await provider.get_quote(inst)
                assert isinstance(quote, Quote)
                iterations += 1
        except BaseException as exc:  # noqa: BLE001 — soak must surface any fault
            last_exception = exc

        await provider.disconnect()

        assert last_exception is None, f"soak failed with: {last_exception!r}"
        assert iterations > 0, "soak did not execute any iterations"
        # No deadlock: we exited the loop and the provider is idle again.
        assert provider.is_connected is False

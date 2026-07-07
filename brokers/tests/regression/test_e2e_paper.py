"""Paper-broker end-to-end workflow regression test.

Exercises the full trading lifecycle against the in-memory
:class:`PaperProvider` (no credentials, no network):

    Platform.paper() -> instrument -> quote -> buy -> positions ->
    balance -> get_orders -> cancel

Borrowed in spirit from ``archive/refance-parallel-sdk/tests/test_e2e.py``
and ``test_soak.py`` but adapted to the ``brokers`` Platform/Provider APIs.
"""

from __future__ import annotations

import pytest

from brokers.domain.enums import Exchange, OrderType
from brokers.domain.values import Balance, OrderResponse, Position, Quote
from brokers.platform import Platform


class TestPaperEndToEnd:
    """Full lifecycle against the paper provider."""

    @pytest.mark.asyncio
    async def test_full_paper_workflow(self) -> None:
        platform = Platform.paper()
        provider = platform.provider

        # Create an instrument
        inst = platform.instrument("RELIANCE", Exchange.NSE)
        assert inst.symbol == "RELIANCE"
        assert inst.exchange == Exchange.NSE

        # Fetch a quote
        quote = await inst.quote()
        assert isinstance(quote, Quote)
        assert quote.ltp > 0

        # Place a market buy
        resp = await inst.buy(1, order_type=OrderType.MARKET)
        assert isinstance(resp, OrderResponse)
        assert resp.order_id
        order_id = resp.order_id

        # Positions reflect the simulated fill
        positions = await provider.get_positions()
        assert isinstance(positions, list)
        assert any(
            isinstance(p, Position) and p.symbol == "RELIANCE" for p in positions
        )

        # Balance is returned and non-negative
        balance = await provider.get_balance()
        assert isinstance(balance, Balance)
        assert balance.available_balance >= 0

        # The order appears in the order book
        orders = await provider.get_orders()
        assert any(o.order_id == order_id for o in orders)

        # Cancel is a valid lifecycle call (paper fills immediately, so this
        # exercises the cancel path without requiring a live open order).
        cancel = await provider.cancel_order(order_id)
        assert isinstance(cancel, OrderResponse)

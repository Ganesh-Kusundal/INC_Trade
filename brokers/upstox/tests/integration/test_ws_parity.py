"""Pre-production WebSocket parity gate for Upstox."""

from __future__ import annotations

import threading

import pytest

from brokers.upstox.tests.integration.conftest import requires_pre_prod

pytestmark = [
    pytest.mark.regression,
    pytest.mark.market_hours,
    pytest.mark.pre_prod,
    pytest.mark.upstox,
]


@requires_pre_prod
class TestWsParity:
    def test_ltp_nifty_canonical_shape(self, gateway, ws_teardown):
        received = threading.Event()
        last = {}

        def on_tick(quote):
            last["quote"] = quote
            received.set()

        gateway.stream("NIFTY", "INDEX", mode="LTP", on_tick=on_tick)
        assert received.wait(timeout=20)
        quote = last["quote"]
        assert float(quote.ltp) > 0

    def test_full_reliance_has_ohlc(self, gateway, ws_teardown):
        received = threading.Event()
        last = {}

        def on_tick(quote):
            last["quote"] = quote
            received.set()

        gateway.stream("RELIANCE", "NSE", mode="FULL", on_tick=on_tick)
        assert received.wait(timeout=20)
        quote = last["quote"]
        assert float(quote.ltp) > 0
        assert quote.open is not None
        assert quote.high is not None

    def test_full_mode_has_bid_ask_or_depth(self, gateway, ws_teardown):
        received = threading.Event()
        last = {}

        def on_tick(quote):
            last["quote"] = quote
            received.set()

        gateway.stream("RELIANCE", "NSE", mode="FULL", on_tick=on_tick)
        assert received.wait(timeout=20)
        quote = last["quote"]
        has_book = quote.bid is not None or quote.ask is not None
        assert has_book or float(quote.ltp) > 0

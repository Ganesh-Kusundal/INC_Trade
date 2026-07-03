"""Live WebSocket parity gate for modern Upstox adapter."""

from __future__ import annotations

import time

from brokers.domain import Quote
from brokers.tests.integration.upstox.conftest import requires_pre_prod, ws_teardown


def _tick_ltp(tick: Quote | dict):
    if isinstance(tick, Quote):
        return tick.ltp
    return tick["ltp"]


@requires_pre_prod
class TestLiveWsParity:
    def test_ltp_tick_shape(self, gateway, ws_teardown):
        ticks = []

        def on_tick(tick):
            ticks.append(tick)

        gateway.streaming.on_tick = on_tick
        gateway.streaming.subscribe("NIFTY", "INDEX")
        gateway.streaming.start()
        deadline = time.time() + 30
        while time.time() < deadline and not ticks:
            time.sleep(0.5)
        gateway.streaming.stop()
        assert ticks, "Expected at least one LTP tick for NIFTY"
        assert _tick_ltp(ticks[0]) > 0

    def test_full_mode_quote_fields(self, gateway, ws_teardown):
        ticks = []

        def on_tick(tick):
            ticks.append(tick)

        gateway.streaming.mode = "full"
        gateway.streaming.on_tick = on_tick
        gateway.streaming.subscribe("RELIANCE", "NSE")
        gateway.streaming.start()
        deadline = time.time() + 30
        while time.time() < deadline and not ticks:
            time.sleep(0.5)
        gateway.streaming.stop()
        assert ticks, "Expected FULL mode tick for RELIANCE"
        assert _tick_ltp(ticks[0]) > 0

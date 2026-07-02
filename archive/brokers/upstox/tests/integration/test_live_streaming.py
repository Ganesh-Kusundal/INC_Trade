"""Live gateway streaming tests for Upstox."""

from __future__ import annotations

import threading
import time

import pytest

from brokers.upstox.tests.integration.conftest import skip_live

pytestmark = [pytest.mark.regression, pytest.mark.market_hours]


@skip_live
class TestLiveStreaming:
    def test_stream_ltp_mode_receives_ticks(self, gateway, ws_teardown):
        received = threading.Event()
        ticks = []

        def on_tick(quote):
            ticks.append(quote)
            received.set()

        gateway.stream("NIFTY", "INDEX", mode="LTP", on_tick=on_tick)
        assert received.wait(timeout=20), "No LTP tick received within 20s"
        assert len(ticks) >= 1

    def test_stream_full_mode_receives_ohlc(self, gateway, ws_teardown):
        received = threading.Event()
        ticks = []

        def on_tick(quote):
            ticks.append(quote)
            received.set()

        gateway.stream("RELIANCE", "NSE", mode="FULL", on_tick=on_tick)
        assert received.wait(timeout=20), "No FULL tick received within 20s"
        if ticks:
            tick = ticks[0]
            assert hasattr(tick, "ltp")
            assert hasattr(tick, "open")

    def test_unstream_stops_callbacks(self, gateway, ws_teardown):
        ticks = []

        def on_tick(quote):
            ticks.append(quote)

        gateway.stream("RELIANCE", "NSE", mode="LTP", on_tick=on_tick)
        time.sleep(2)
        gateway.unstream("RELIANCE", "NSE", on_tick=on_tick)
        count_after_unsub = len(ticks)
        time.sleep(2)
        assert len(ticks) <= count_after_unsub + 5

    def test_multiple_symbol_streams(self, gateway, ws_teardown):
        received = {"RELIANCE": threading.Event(), "TCS": threading.Event()}

        def make_handler(symbol: str):
            def on_tick(_quote):
                received[symbol].set()

            return on_tick

        gateway.stream("RELIANCE", "NSE", mode="LTP", on_tick=make_handler("RELIANCE"))
        gateway.stream("TCS", "NSE", mode="LTP", on_tick=make_handler("TCS"))
        for event in received.values():
            assert event.wait(timeout=25), "Expected ticks on both symbols"

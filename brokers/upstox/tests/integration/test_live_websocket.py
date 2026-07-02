"""Live integration tests for Upstox WebSocket feeds."""

from __future__ import annotations

import threading

import pytest

from brokers.upstox.tests.integration.conftest import skip_live

pytestmark = [pytest.mark.regression, pytest.mark.market_hours]


@skip_live
class TestLiveWebSocket:
    def test_market_multiplexer_default_disconnected(self, gateway):
        mux = gateway._broker.market_data_websocket
        assert mux.is_connected is False

    def test_portfolio_stream_default_disconnected(self, gateway):
        stream = gateway._broker.portfolio_stream
        assert stream.is_connected is False

    def test_market_listener_registration(self, gateway):
        mux = gateway._broker.market_data_websocket
        received = []

        def listener(event_type, payload):
            received.append((event_type, payload))

        mux.add_listener(listener)
        assert listener in mux._listeners
        mux.remove_listener(listener)
        assert listener not in mux._listeners

    def test_portfolio_connect_smoke(self, gateway, ws_teardown):
        """Portfolio stream should connect without crashing."""
        from brokers.common.async_compat import run_async_compat

        stream = gateway._broker.portfolio_stream
        run_async_compat(stream.connect(), fire_and_forget=False)
        assert stream.is_connected is True
        run_async_compat(stream.disconnect(), fire_and_forget=False)
        assert stream.is_connected is False

    def test_market_stream_receives_ltp_tick(self, gateway, ws_teardown):
        """Subscribe to NIFTY LTP and receive at least one tick."""
        received = threading.Event()
        ticks = []

        def on_tick(quote):
            ticks.append(quote)
            received.set()

        gateway.stream("NIFTY", "INDEX", mode="LTP", on_tick=on_tick)
        assert received.wait(timeout=20), "No LTP tick received within 20s"
        assert len(ticks) >= 1
        assert float(ticks[0].ltp) > 0

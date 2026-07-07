"""Tests for Dhan streaming modules — payloads, decoder, market feed, order feed."""

from __future__ import annotations

import json


from brokers.dhan.streaming.decoder import decode_market_message
from brokers.dhan.streaming.payloads import (
    build_subscribe_payload,
    build_unsubscribe_payload,
    format_instrument_key,
    mode_to_feed_type,
)
from brokers.domain.enums import Exchange


# ── Payload builder tests ──────────────────────────────────────────────────


class TestFormatInstrumentKey:
    def test_nse_equity(self):
        assert format_instrument_key(Exchange.NSE, "1333") == "NSE_EQ|1333"

    def test_bse_equity(self):
        assert format_instrument_key(Exchange.BSE, "500325") == "BSE_EQ|500325"

    def test_nfo(self):
        assert format_instrument_key(Exchange.NFO, "43425") == "NSE_FNO|43425"

    def test_index(self):
        assert format_instrument_key(Exchange.INDEX, "13") == "IDX_I|13"


class TestBuildSubscribePayload:
    def test_basic_subscribe(self):
        payload = build_subscribe_payload(
            [(Exchange.NSE, "1333"), (Exchange.NSE, "11536")],
            feed_type="quote",
        )
        data = json.loads(payload)
        assert data["action"] == "subscribe"
        assert "NSE_EQ|1333" in data["instruments"]
        assert "NSE_EQ|11536" in data["instruments"]
        assert data["feedType"] == "quote"

    def test_depth_subscribe(self):
        payload = build_subscribe_payload(
            [(Exchange.NSE, "1333")],
            feed_type="depth",
        )
        data = json.loads(payload)
        assert data["feedType"] == "depth"

    def test_empty_instruments(self):
        payload = build_subscribe_payload([], feed_type="ltp")
        data = json.loads(payload)
        assert data["instruments"] == []


class TestBuildUnsubscribePayload:
    def test_basic_unsubscribe(self):
        payload = build_unsubscribe_payload(
            [(Exchange.NSE, "1333")],
            feed_type="quote",
        )
        data = json.loads(payload)
        assert data["action"] == "unsubscribe"
        assert "NSE_EQ|1333" in data["instruments"]


class TestModeToFeedType:
    def test_ltp(self):
        assert mode_to_feed_type("ltp") == "ltp"

    def test_quote(self):
        assert mode_to_feed_type("quote") == "quote"

    def test_full_maps_to_depth(self):
        assert mode_to_feed_type("full") == "depth"

    def test_depth(self):
        assert mode_to_feed_type("depth") == "depth"

    def test_unknown_defaults_to_quote(self):
        assert mode_to_feed_type("unknown") == "quote"


# ── Decoder tests ──────────────────────────────────────────────────────────


class TestDecodeMarketMessage:
    def test_quote_tick(self):
        raw = json.dumps({
            "instrument_key": "NSE_EQ|1333",
            "trading_symbol": "RELIANCE",
            "ltp": 2500.5,
            "open": 2490.0,
            "high": 2510.0,
            "low": 2480.0,
            "close": 2505.0,
            "volume": 100000,
        })
        events = decode_market_message(raw)
        assert len(events) == 1
        tick = events[0]
        assert tick.symbol == "RELIANCE"
        assert tick.ltp == 2500.5
        assert tick.open == 2490.0
        assert tick.high == 2510.0
        assert tick.low == 2480.0
        assert tick.close == 2505.0
        assert tick.volume == 100000
        assert tick.broker_id == "dhan"

    def test_ltp_tick(self):
        raw = json.dumps({
            "instrument_key": "NSE_EQ|1333",
            "ltp": 2500.5,
        })
        events = decode_market_message(raw)
        assert len(events) == 1
        assert events[0].ltp == 2500.5

    def test_zero_ltp_filtered(self):
        raw = json.dumps({
            "instrument_key": "NSE_EQ|1333",
            "ltp": 0,
        })
        events = decode_market_message(raw)
        assert len(events) == 0

    def test_depth_tick(self):
        raw = json.dumps({
            "instrument_key": "NSE_EQ|1333",
            "trading_symbol": "RELIANCE",
            "ltp": 2500.5,
            "depth": {
                "buy": [
                    {"price": 2500.0, "qty": 100},
                    {"price": 2499.0, "qty": 200},
                ],
                "sell": [
                    {"price": 2501.0, "qty": 150},
                    {"price": 2502.0, "qty": 250},
                ],
            },
        })
        events = decode_market_message(raw)
        assert len(events) == 1
        tick = events[0]
        assert len(tick.depth_bids) == 2
        assert len(tick.depth_asks) == 2
        assert tick.depth_bids[0] == (2500.0, 100)
        assert tick.depth_asks[0] == (2501.0, 150)
        assert tick.is_depth is True

    def test_order_update(self):
        raw = json.dumps({
            "Type": "order_alert",
            "orderNo": "123456",
            "tradingSymbol": "RELIANCE",
            "orderStatus": "TRADED",
            "transactionType": "BUY",
            "filledQty": 10,
            "avgTradePrice": 2500.5,
        })
        events = decode_market_message(raw)
        assert len(events) == 1
        order = events[0]
        assert order.order_id == "123456"
        assert order.symbol == "RELIANCE"
        assert order.status == "FILLED"
        assert order.side == "BUY"
        assert order.filled_quantity == 10
        assert order.broker_id == "dhan"

    def test_order_status_normalization(self):
        for dhan_status, expected in [
            ("TRANSIT", "OPEN"),
            ("PENDING", "OPEN"),
            ("OPEN", "OPEN"),
            ("TRADED", "FILLED"),
            ("PART_TRADED", "PARTIALLY_FILLED"),
            ("EXPIRED", "EXPIRED"),
            ("REJECTED", "REJECTED"),
            ("CANCELLED", "CANCELLED"),
        ]:
            raw = json.dumps({
                "Type": "order_alert",
                "orderNo": "1",
                "orderStatus": dhan_status,
            })
            events = decode_market_message(raw)
            assert len(events) == 1, f"Failed for {dhan_status}"
            assert events[0].status == expected, f"{dhan_status} -> {events[0].status}, expected {expected}"

    def test_batch_messages(self):
        raw = json.dumps([
            {"ltp": 2500.5, "instrument_key": "NSE_EQ|1333", "trading_symbol": "RELIANCE"},
            {"ltp": 3500.0, "instrument_key": "NSE_EQ|11536", "trading_symbol": "TCS"},
        ])
        events = decode_market_message(raw)
        assert len(events) == 2

    def test_invalid_json(self):
        events = decode_market_message("not valid json")
        assert events == []

    def test_empty_message(self):
        events = decode_market_message("{}")
        assert events == []

    def test_bytes_input(self):
        raw = json.dumps({
            "instrument_key": "NSE_EQ|1333",
            "trading_symbol": "RELIANCE",
            "ltp": 2500.5,
        }).encode()
        events = decode_market_message(raw)
        assert len(events) == 1

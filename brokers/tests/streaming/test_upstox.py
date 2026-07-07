"""Tests for Upstox streaming modules — payloads, subscription manager, authorizer, decoder."""

from __future__ import annotations

import json

import pytest

from brokers.upstox.streaming.payloads import (
    build_subscribe_payload,
    build_unsubscribe_payload,
    build_change_mode_payload,
    encode_payload,
    normalize_mode,
)
from brokers.upstox.streaming.subscription_manager import (
    PlanTier,
    SubscriptionLimitExceededError,
    UpstoxV3SubscriptionManager,
)


# ── Payload builder tests ──────────────────────────────────────────────────


class TestNormalizeMode:
    def test_ltp_variants(self):
        assert normalize_mode("ltp") == "ltpc"
        assert normalize_mode("ltpc") == "ltpc"
        assert normalize_mode("LTP") == "ltpc"

    def test_quote_variants(self):
        assert normalize_mode("quote") == "full"
        assert normalize_mode("full") == "full"
        assert normalize_mode("FULL") == "full"

    def test_greeks_variants(self):
        assert normalize_mode("option_greeks") == "option_greeks"
        assert normalize_mode("greeks") == "option_greeks"

    def test_depth_variants(self):
        assert normalize_mode("full_d30") == "full_d30"
        assert normalize_mode("d30") == "full_d30"
        assert normalize_mode("depth") == "full_d30"

    def test_unknown_defaults_to_ltpc(self):
        assert normalize_mode("unknown") == "ltpc"
        assert normalize_mode("") == "ltpc"


class TestBuildSubscribePayload:
    def test_basic_subscribe(self):
        payload = build_subscribe_payload(
            ["NSE_EQ|INE002A01018", "NSE_EQ|INE012A01024"],
            mode="ltpc",
        )
        assert payload["method"] == "subscribe"
        assert "NSE_EQ|INE002A01018" in payload["data"]["instrumentKeys"]
        assert "NSE_EQ|INE012A01024" in payload["data"]["instrumentKeys"]
        assert payload["data"]["mode"] == "ltpc"
        assert "guid" in payload

    def test_full_mode(self):
        payload = build_subscribe_payload(
            ["NSE_EQ|INE002A01018"],
            mode="full",
        )
        assert payload["data"]["mode"] == "full"

    def test_empty_instruments(self):
        payload = build_subscribe_payload([], mode="ltpc")
        assert payload["data"]["instrumentKeys"] == []


class TestBuildUnsubscribePayload:
    def test_basic_unsubscribe(self):
        payload = build_unsubscribe_payload(["NSE_EQ|INE002A01018"], mode="ltpc")
        assert payload["method"] == "unsubscribe"
        assert "NSE_EQ|INE002A01018" in payload["data"]["instrumentKeys"]


class TestBuildChangeModePayload:
    def test_change_mode(self):
        payload = build_change_mode_payload(["NSE_EQ|INE002A01018"], mode="full")
        assert payload["method"] == "change_mode"
        assert payload["data"]["mode"] == "full"


class TestEncodePayload:
    def test_encode_to_bytes(self):
        payload = build_subscribe_payload(["NSE_EQ|INE002A01018"], mode="ltpc")
        encoded = encode_payload(payload)
        assert isinstance(encoded, bytes)
        decoded = json.loads(encoded)
        assert decoded["method"] == "subscribe"


# ── Subscription manager tests ─────────────────────────────────────────────


class TestUpstoxV3SubscriptionManager:
    def test_initial_state(self):
        mgr = UpstoxV3SubscriptionManager()
        assert mgr.active_count == 0
        assert mgr.tier == PlanTier.STANDARD

    def test_subscribe_basic(self):
        mgr = UpstoxV3SubscriptionManager()
        mgr.subscribe(["NSE_EQ|INE002A01018", "NSE_EQ|INE012A01024"], mode="ltpc")
        assert mgr.active_count == 2
        assert mgr.get_mode("NSE_EQ|INE002A01018") == "ltpc"

    def test_subscribe_respects_total_limit(self):
        mgr = UpstoxV3SubscriptionManager(tier=PlanTier.STANDARD)
        instruments = [f"NSE_EQ|INST{i:04d}" for i in range(25)]
        mgr.subscribe(instruments, mode="ltpc")
        assert mgr.active_count == 25

        with pytest.raises(SubscriptionLimitExceededError, match="total limit"):
            mgr.subscribe(["NSE_EQ|EXTRA001"], mode="ltpc")

    def test_subscribe_respects_mode_limit(self):
        mgr = UpstoxV3SubscriptionManager()
        instruments = [f"NSE_EQ|INST{i:04d}" for i in range(20)]
        mgr.subscribe(instruments, mode="full_d30")
        assert mgr.active_count == 20

        with pytest.raises(SubscriptionLimitExceededError, match="full_d30 limit"):
            mgr.subscribe(["NSE_EQ|EXTRA001"], mode="full_d30")

    def test_unsubscribe(self):
        mgr = UpstoxV3SubscriptionManager()
        mgr.subscribe(["NSE_EQ|INE002A01018", "NSE_EQ|INE012A01024"], mode="ltpc")
        assert mgr.active_count == 2

        mgr.unsubscribe(["NSE_EQ|INE002A01018"])
        assert mgr.active_count == 1
        assert mgr.get_mode("NSE_EQ|INE002A01018") is None

    def test_clear(self):
        mgr = UpstoxV3SubscriptionManager()
        mgr.subscribe(["NSE_EQ|INE002A01018"], mode="ltpc")
        mgr.clear()
        assert mgr.active_count == 0

    def test_get_instruments_by_mode(self):
        mgr = UpstoxV3SubscriptionManager()
        mgr.subscribe(["NSE_EQ|A", "NSE_EQ|B"], mode="ltpc")
        mgr.subscribe(["NSE_EQ|C"], mode="full")

        ltpc = mgr.get_instruments_by_mode("ltpc")
        assert "NSE_EQ|A" in ltpc
        assert "NSE_EQ|B" in ltpc
        assert len(ltpc) == 2

        full = mgr.get_instruments_by_mode("full")
        assert full == ["NSE_EQ|C"]

    def test_mode_change_with_resubscribe(self):
        """Re-subscribing an instrument with a different mode should update counts correctly."""
        mgr = UpstoxV3SubscriptionManager()
        mgr.subscribe(["NSE_EQ|A"], mode="ltpc")
        assert mgr.get_mode("NSE_EQ|A") == "ltpc"

        # Change mode for same instrument
        mgr.subscribe(["NSE_EQ|A"], mode="full")
        assert mgr.get_mode("NSE_EQ|A") == "full"
        assert mgr.active_count == 1  # Still only 1 instrument

    def test_plus_tier(self):
        mgr = UpstoxV3SubscriptionManager(tier=PlanTier.PLUS)
        instruments = [f"NSE_EQ|INST{i:04d}" for i in range(50)]
        mgr.subscribe(instruments, mode="ltpc")
        assert mgr.active_count == 50


# ── Authorizer tests ───────────────────────────────────────────────────────


class TestAuthorizerExtractUrl:
    def test_v3_format(self):
        from brokers.upstox.streaming.authorizer import UpstoxFeedAuthorizer
        response = {"authorized_redirect_uri": "wss://api.upstox.com/v3/feed?token=abc"}
        url = UpstoxFeedAuthorizer._extract_authorized_url(response)
        assert url == "wss://api.upstox.com/v3/feed?token=abc"

    def test_v2_format(self):
        from brokers.upstox.streaming.authorizer import UpstoxFeedAuthorizer
        response = {"redirect_uri": "wss://api.upstox.com/v2/feed?token=abc"}
        url = UpstoxFeedAuthorizer._extract_authorized_url(response)
        assert url == "wss://api.upstox.com/v2/feed?token=abc"

    def test_nested_data_format(self):
        from brokers.upstox.streaming.authorizer import UpstoxFeedAuthorizer
        response = {"data": {"authorized_redirect_uri": "wss://api.upstox.com/v3/feed?token=abc"}}
        url = UpstoxFeedAuthorizer._extract_authorized_url(response)
        assert url == "wss://api.upstox.com/v3/feed?token=abc"

    def test_no_url_returns_none(self):
        from brokers.upstox.streaming.authorizer import UpstoxFeedAuthorizer
        url = UpstoxFeedAuthorizer._extract_authorized_url({"status": "ok"})
        assert url is None

    def test_non_dict_returns_none(self):
        from brokers.upstox.streaming.authorizer import UpstoxFeedAuthorizer
        url = UpstoxFeedAuthorizer._extract_authorized_url("not a dict")
        assert url is None


# ── Decoder tests (basic — protobuf-dependent) ─────────────────────────────


class TestDecoder:
    def test_string_input_returns_empty(self):
        from brokers.upstox.streaming.decoder import decode_market_message
        events = decode_market_message("json message")
        assert events == []

    def test_empty_bytes_returns_empty(self):
        from brokers.upstox.streaming.decoder import decode_market_message
        events = decode_market_message(b"")
        assert events == []

    def test_non_protobuf_bytes_returns_empty(self):
        from brokers.upstox.streaming.decoder import decode_market_message
        events = decode_market_message(b"not protobuf data")
        assert events == []

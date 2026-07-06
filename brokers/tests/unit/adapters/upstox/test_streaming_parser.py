"""Unit tests for Upstox streaming decoder and message building."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from brokers.adapters.upstox.streaming import UpstoxStreaming, UpstoxV3Decoder

PROTO_PATCH = "brokers.adapters.upstox.proto.market_feed_pb2.FeedResponse"


class TestUpstoxV3Decoder:
    def test_parse_empty(self):
        decoder = UpstoxV3Decoder()
        assert decoder.parse(b"") is None

    @patch(PROTO_PATCH)
    def test_parse_valid(self, mock_feed):
        mock_response = MagicMock()
        mock_response.feeds = {}
        mock_feed.return_value = mock_response
        decoder = UpstoxV3Decoder()
        result = decoder.parse(b"fake protobuf")
        assert result == []

    @patch(PROTO_PATCH)
    def test_parse_invalid_protobuf(self, mock_feed):
        mock_feed.side_effect = Exception("bad data")
        decoder = UpstoxV3Decoder()
        assert decoder.parse(b"\xff\xfe") is None

    @patch(PROTO_PATCH)
    def test_parse_feeds_multiple(self, mock_feed):
        feed1 = MagicMock()
        feed1.WhichOneof.return_value = "ltpc"
        feed1.ltpc.ltp = 100
        feed1.ltpc.ltt = 1000
        feed1.ltpc.ltq = 50
        feed1.ltpc.cp = 95
        feed2 = MagicMock()
        feed2.WhichOneof.return_value = "ltpc"
        feed2.ltpc.ltp = 200
        feed2.ltpc.ltt = 2000
        feed2.ltpc.ltq = 10
        feed2.ltpc.cp = 190

        mock_response = MagicMock()
        mock_response.feeds = {"NSE_EQ|STOCK1": feed1, "NSE_EQ|STOCK2": feed2}
        mock_feed.return_value = mock_response

        decoder = UpstoxV3Decoder()
        result = decoder.parse(b"data")
        assert len(result) == 2
        assert result[0]["ltp"] == 100
        assert result[1]["ltp"] == 200

    def test_feed_to_dict_ltpc(self):
        feed = MagicMock()
        feed.WhichOneof.return_value = "ltpc"
        feed.ltpc.ltp = 150
        feed.ltpc.ltt = 500
        feed.ltpc.ltq = 25
        feed.ltpc.cp = 140
        result = UpstoxV3Decoder._feed_to_dict_v3(feed, "NSE_EQ|RELIANCE")
        assert result["symbol"] == "RELIANCE"
        assert result["ltp"] == 150
        assert result["timestamp"] == 500
        assert result["volume"] == 25
        assert result["close"] == 140

    def test_feed_to_dict_first_level_with_greeks(self):
        feed = MagicMock()
        feed.WhichOneof.return_value = "firstLevelWithGreeks"
        feed.firstLevelWithGreeks.HasField.return_value = True
        feed.firstLevelWithGreeks.ltpc.ltp = 50
        feed.firstLevelWithGreeks.ltpc.ltt = 100
        feed.firstLevelWithGreeks.ltpc.cp = 45
        feed.firstLevelWithGreeks.vtt = 1000
        feed.firstLevelWithGreeks.oi = 5000
        feed.firstLevelWithGreeks.iv = 25.5
        result = UpstoxV3Decoder._feed_to_dict_v3(feed, "NSE_FO|NIFTY")
        assert result["ltp"] == 50
        assert result["oi"] == 5000
        assert result["iv"] == 25.5

    def test_feed_to_dict_full_feed_market_ff(self):
        feed = MagicMock()
        feed.WhichOneof.return_value = "fullFeed"
        feed.fullFeed.WhichOneof.return_value = "marketFF"
        feed.fullFeed.marketFF.HasField.return_value = True
        feed.fullFeed.marketFF.ltpc.ltp = 300
        feed.fullFeed.marketFF.ltpc.ltt = 999
        feed.fullFeed.marketFF.ltpc.cp = 290
        feed.fullFeed.marketFF.vtt = 2000
        feed.fullFeed.marketFF.oi = 10000
        feed.fullFeed.marketFF.iv = 30.0
        feed.fullFeed.marketFF.marketLevel.bidAskQuote = []
        feed.fullFeed.marketFF.marketOHLC.ohlc = []
        result = UpstoxV3Decoder._feed_to_dict_v3(feed, "NSE_EQ|INFY")
        assert result["ltp"] == 300
        assert result["oi"] == 10000

    def test_feed_to_dict_full_feed_with_depth_and_ohlc(self):
        feed = MagicMock()
        feed.WhichOneof.return_value = "fullFeed"
        feed.fullFeed.WhichOneof.return_value = "marketFF"
        feed.fullFeed.marketFF.HasField.return_value = True
        feed.fullFeed.marketFF.ltpc.ltp = 100
        feed.fullFeed.marketFF.ltpc.ltt = 1
        feed.fullFeed.marketFF.ltpc.cp = 90
        feed.fullFeed.marketFF.vtt = 500
        feed.fullFeed.marketFF.oi = 2000
        feed.fullFeed.marketFF.iv = 20.0

        bid = MagicMock()
        bid.bidP = 99
        bid.bidQ = 10
        bid.askP = 101
        bid.askQ = 5
        feed.fullFeed.marketFF.marketLevel.bidAskQuote = [bid]

        ohlc = MagicMock()
        ohlc.open = 95
        ohlc.high = 105
        ohlc.low = 90
        ohlc.close = 100
        feed.fullFeed.marketFF.marketOHLC.ohlc = [ohlc]

        result = UpstoxV3Decoder._feed_to_dict_v3(feed, "NSE_EQ|TCS")
        assert result["depth"]["bids"][0]["price"] == 99
        assert result["depth"]["asks"][0]["price"] == 101
        assert result["ohlc"]["open"] == 95


class TestUpstoxStreamingInit:
    def test_initial_state(self):
        s = UpstoxStreaming(access_token="tok")
        assert s.mode == "ltpc"
        assert s.on_depth is None
        assert s._authorized_url == ""

    def test_mode_setter(self):
        s = UpstoxStreaming(access_token="tok")
        s.mode = "full"
        assert s.mode == "full"

    def test_on_depth_setter(self):
        cb = lambda x: None
        s = UpstoxStreaming(access_token="tok")
        s.on_depth = cb
        assert s.on_depth is cb


class TestUpstoxStreamingSubscribe:
    @patch("brokers.adapters.upstox.streaming.resolve_upstox_instrument_key")
    def test_subscribe_resolves_key(self, mock_resolve):
        mock_resolve.return_value = "NSE_EQ|RELIANCE"
        s = UpstoxStreaming(access_token="tok")
        s.subscribe("RELIANCE", "NSE")
        mock_resolve.assert_called_once_with("RELIANCE", "NSE", None)

    @patch("brokers.adapters.upstox.streaming.resolve_upstox_instrument_key")
    def test_unsubscribe_resolves_key(self, mock_resolve):
        mock_resolve.return_value = "NSE_EQ|RELIANCE"
        s = UpstoxStreaming(access_token="tok")
        s.unsubscribe("RELIANCE", "NSE")
        mock_resolve.assert_called_once_with("RELIANCE", "NSE", None)


class TestUpstoxStreamingMessages:
    def test_build_subscribe_message(self):
        s = UpstoxStreaming(access_token="tok")
        msg = json.loads(s._build_subscribe_message(["K1", "K2"]))
        assert msg["method"] == "sub"
        assert msg["data"]["mode"] == "ltpc"
        assert msg["data"]["instrumentKeys"] == ["K1", "K2"]

    def test_build_unsubscribe_message(self):
        s = UpstoxStreaming(access_token="tok")
        msg = json.loads(s._build_unsubscribe_message(["K1"]))
        assert msg["method"] == "unsub"
        assert msg["data"]["instrumentKeys"] == ["K1"]


class TestUpstoxStreamingOnMessage:
    @patch("brokers.adapters.upstox.streaming.frame_to_tick_dict")
    @patch("brokers.adapters.upstox.streaming.frame_to_quote")
    def test_on_message_binary(self, mock_quote, mock_tick):
        mock_quote.return_value = None
        mock_tick.return_value = {"ltp": 100}
        s = UpstoxStreaming(access_token="tok")
        ticks = []
        s._on_tick = lambda t: ticks.append(t)
        with patch.object(s._decoder, "parse", return_value=[{"ltp": 100}]):
            s._on_message(None, b"\x00\x01")
        assert len(ticks) == 1

    def test_on_message_text_market_info(self):
        s = UpstoxStreaming(access_token="tok")
        s._on_message(None, json.dumps({"type": "market_info"}))

    def test_on_message_text_invalid_json(self):
        s = UpstoxStreaming(access_token="tok")
        s._on_message(None, "not json {")

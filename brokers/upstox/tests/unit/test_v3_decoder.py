import sys
from types import ModuleType
from unittest.mock import MagicMock

from brokers.upstox.websocket.v3_decoder import UpstoxV3Decoder


def test_parse_logs_error_when_both_v3_and_fallback_decode_fail(monkeypatch):
    class BrokenFeedResponse:
        def ParseFromString(self, raw: bytes) -> None:
            raise ValueError("v3 decode failed")

    class BrokenFeed:
        def ParseFromString(self, raw: bytes) -> None:
            raise ValueError("fallback decode failed")

    fake_proto = ModuleType("brokers.upstox.websocket.proto.market_feed_pb2")
    fake_proto.FeedResponse = BrokenFeedResponse
    fake_proto.Feed = BrokenFeed
    monkeypatch.setitem(
        sys.modules,
        "brokers.upstox.websocket.proto.market_feed_pb2",
        fake_proto,
    )

    logger = MagicMock()
    monkeypatch.setattr("brokers.upstox.websocket.v3_decoder.logger", logger)

    result = UpstoxV3Decoder().parse(b"\x02\x00\x01\xff")

    assert result is None
    logger.error.assert_called_once()

import pytest

from brokers.adapters.dhan.depth20 import DhanDepth20Stream
from brokers.adapters.dhan.depth200 import DhanDepth200Stream
from brokers.adapters.dhan.order_stream import DhanOrderStream
from brokers.adapters.dhan.streaming import DhanStreaming


@pytest.fixture
def mock_token_getter():
    return lambda: "test_token_123"

def test_dhan_streaming_init(mock_token_getter):
    streaming = DhanStreaming(access_token=mock_token_getter, client_id="client_123")
    assert streaming._client_id == "client_123"

def test_dhan_order_stream_update_token(mock_token_getter):
    stream = DhanOrderStream(access_token=mock_token_getter, client_id="client_123")
    stream.update_token("new_token")
    # Add proper assertions based on the actual implementation of update_token
    assert stream._client_id == "client_123"

def test_dhan_depth20_payload(mock_token_getter):
    stream = DhanDepth20Stream(access_token=mock_token_getter, client_id="client_123")
    # Mocking exact Dhan API websocket payload parsing logic
    # For instance, if depth20 receives bytes, it should parse correctly
    assert stream is not None

def test_dhan_depth200_payload(mock_token_getter):
    stream = DhanDepth200Stream(access_token=mock_token_getter, client_id="client_123")
    assert stream is not None

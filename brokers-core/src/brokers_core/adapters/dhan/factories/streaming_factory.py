"""Streaming factory — streaming and order stream creation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NamedTuple

from brokers_core.adapters.dhan.depth20 import DhanDepth20Stream
from brokers_core.adapters.dhan.depth200 import DhanDepth200Stream
from brokers_core.adapters.dhan.order_stream import DhanOrderStream
from brokers_core.adapters.dhan.streaming import DhanStreaming

if TYPE_CHECKING:
    from brokers_core.adapters.dhan.identity import DhanInstrumentResolver


class StreamingComponents(NamedTuple):
    """Streaming-related components."""

    streaming: DhanStreaming
    order_stream: DhanOrderStream
    depth20_stream: DhanDepth20Stream
    depth200_stream: DhanDepth200Stream


def create_streams(
    auth: Any,
    client_id: str,
    resolver: DhanInstrumentResolver,
) -> StreamingComponents:
    """Create all streaming components.

    Args:
        auth: DhanAuth instance (uses get_token callable).
        client_id: Dhan client ID.
        resolver: Instrument resolver for symbol mapping.

    Returns:
        StreamingComponents namedtuple with all streaming services.
    """
    streaming = DhanStreaming(
        access_token=auth.get_token,
        client_id=client_id,
        resolver=resolver,
    )

    order_stream = DhanOrderStream(
        access_token=auth.get_token,
        client_id=client_id,
    )

    depth20_stream = DhanDepth20Stream(
        access_token=auth.get_token,
        client_id=client_id,
        resolver=resolver,
    )

    depth200_stream = DhanDepth200Stream(
        access_token=auth.get_token,
        client_id=client_id,
        resolver=resolver,
    )

    return StreamingComponents(
        streaming=streaming,
        order_stream=order_stream,
        depth20_stream=depth20_stream,
        depth200_stream=depth200_stream,
    )

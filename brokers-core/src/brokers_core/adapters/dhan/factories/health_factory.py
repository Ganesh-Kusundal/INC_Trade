"""Health factory — health reporter creation."""

from __future__ import annotations

from typing import Any, NamedTuple

from brokers_core.adapters.dhan.auth import DhanAuth
from brokers_core.adapters.dhan.connection_manager import DhanConnectionManager
from brokers_core.adapters.dhan.health_reporter import DhanHealthReporter


class HealthComponents(NamedTuple):
    """Health-related components."""

    health_reporter: DhanHealthReporter


def create_health_reporter(
    auth: DhanAuth,
    connection_manager: DhanConnectionManager,
    http_client: Any,
    streaming: Any,
    order_stream: Any,
    depth20_stream: Any,
    depth200_stream: Any,
) -> HealthComponents:
    """Create health reporter.

    Args:
        auth: DhanAuth instance.
        connection_manager: DhanConnectionManager instance.
        http_client: HTTP client instance.
        streaming: Streaming service instance.
        order_stream: Order stream instance.
        depth20_stream: Depth20 stream instance.
        depth200_stream: Depth200 stream instance.

    Returns:
        HealthComponents namedtuple with health_reporter.
    """
    health_reporter = DhanHealthReporter(
        auth=auth,
        connection_manager=connection_manager,
        http_client=http_client,
        streaming=streaming,
        order_stream=order_stream,
        depth20_stream=depth20_stream,
        depth200_stream=depth200_stream,
    )

    return HealthComponents(health_reporter=health_reporter)

"""DataLake gateway stub."""

from __future__ import annotations

from typing import Any


class DataLakeGateway:
    """Stub data lake gateway for test compatibility."""

    def __init__(self, root: str = "", **kwargs: Any) -> None:
        self._root = root

    def stream(self, symbols: list[str], **kwargs: Any) -> None:
        from brokers.common.gateway_errors import UnsupportedGatewayOperationError

        raise UnsupportedGatewayOperationError("DataLakeGateway", "streaming")

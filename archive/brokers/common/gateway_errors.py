"""Read-only gateway operations not supported by a gateway implementation."""

from __future__ import annotations

from brokers.common.resilience.errors import TradeXV2Error


class UnsupportedGatewayOperationError(NotImplementedError, TradeXV2Error):
    """Raised when a gateway does not implement a contract method."""

    def __init__(self, gateway: str, operation: str) -> None:
        super().__init__(f"{gateway} does not support {operation}")
        self.gateway = gateway
        self.operation = operation

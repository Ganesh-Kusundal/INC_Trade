"""Typed errors for broker connection bootstrap."""

from __future__ import annotations

from brokers.common.connection.bootstrap_result import BootstrapResult, BootstrapStatus
from brokers.common.resilience.errors import TradeXV2Error


class BrokerNotReadyError(TradeXV2Error):
    """Raised when a broker gateway is unavailable or not authenticated."""

    def __init__(
        self,
        message: str,
        *,
        broker: str,
        status: BootstrapStatus,
        bootstrap: BootstrapResult | None = None,
    ) -> None:
        super().__init__(message)
        self.broker = broker
        self.status = status
        self.bootstrap = bootstrap

    @classmethod
    def from_bootstrap(cls, result: BootstrapResult) -> BrokerNotReadyError:
        return cls(
            result.error or f"{result.broker} bootstrap failed: {result.status.value}",
            broker=result.broker,
            status=result.status,
            bootstrap=result,
        )

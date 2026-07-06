"""Risk manager port — hexagonal boundary for pre-trade checks."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from brokers_core.domain import RiskCheckRequest, RiskCheckResult


@runtime_checkable
class RiskManagerPort(Protocol):
    """Pre-trade risk validation invoked by broker order adapters."""

    def get_status(self) -> dict[str, str]: ...

    def is_kill_switch_active(self) -> bool: ...

    def check_order(self, order_request: RiskCheckRequest) -> RiskCheckResult: ...

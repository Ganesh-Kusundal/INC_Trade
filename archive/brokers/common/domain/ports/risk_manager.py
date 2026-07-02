"""Risk manager port — hexagonal boundary between broker and application layers."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RiskManagerPort(Protocol):
    """Port that the broker layer depends on for pre-trade risk checks.

    The concrete :class:`application.oms.risk_manager.RiskManager` satisfies
    this Protocol.  Broker modules MUST import this port rather than the
    concrete class so that the dependency rule of hexagonal architecture is
    preserved (brokers → domain ports, not brokers → application).
    """

    def get_status(self) -> dict[str, Any]: ...

    def is_kill_switch_active(self) -> bool: ...

    def check_order(self, order_request: Any) -> Any:
        """Validate an order request against risk rules.

        Parameters
        ----------
        order_request:
            A domain Order (or structurally compatible object) to
            validate.

        Returns
        -------
        Any
            A RiskResult-shaped object with at least allowed: bool
            and reason: str | None attributes.
        """
        ...


__all__ = ["RiskManagerPort"]

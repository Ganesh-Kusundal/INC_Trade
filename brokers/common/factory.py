"""BrokerProviderFactory — abstract interface for broker factory implementations.

Both BrokerFactory (Dhan) and UpstoxBrokerFactory should implement this
interface so BrokerService can call either factory polymorphically.

.. note::
    This factory returns ``MarketDataGateway`` (the legacy ABC). To use the
    new ``CommonBrokerGateway`` Protocol, wrap the result with
    ``brokers.common.adapters.wrap_market_gateway()``.  See
    ``brokers.common.bootstrap`` for the full wiring sequence.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from brokers.common.gateway import MarketDataGateway

if TYPE_CHECKING:
    from application.oms.risk_manager import RiskManager
    from infrastructure.event_bus import EventBus
    from infrastructure.lifecycle import LifecycleManager


class BrokerProviderFactory(ABC):
    """Abstract factory for creating configured MarketDataGateway instances."""

    @abstractmethod
    def create(
        self,
        *,
        env_path: Path | None = None,
        load_instruments: bool = True,
        event_bus: EventBus | None = None,
        risk_manager: RiskManager | None = None,
        lifecycle: LifecycleManager | None = None,
    ) -> MarketDataGateway:
        """Create a configured MarketDataGateway for this broker.

        Parameters
        ----------
        env_path:
            Path to the .env file with broker credentials.
        load_instruments:
            Whether to load the instrument master on creation.
        event_bus:
            Optional EventBus for domain event publishing.
        risk_manager:
            Optional RiskManager for pre-trade risk checks.
        lifecycle:
            Optional LifecycleManager for managed service registration.
        """
        ...

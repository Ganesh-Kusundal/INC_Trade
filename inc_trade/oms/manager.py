"""Broker Manager — holds and manages multiple broker connections."""

from __future__ import annotations

import logging
from typing import Any

from inc_trade.domain.enums import BrokerID
from inc_trade.services.broker_facade import BrokerFacade
from inc_trade.oms.router import OrderRouter
from inc_trade.domain.entities import OrderRequest
from inc_trade.domain import OrderResponse

logger = logging.getLogger(__name__)


class BrokerManager:
    """Manages active broker connections and provides centralized routing."""
    
    def __init__(self) -> None:
        self._brokers: dict[BrokerID, BrokerFacade] = {}
        self._router = OrderRouter(self)
        
    def register_broker(self, broker: BrokerFacade) -> None:
        """Register an active broker facade."""
        self._brokers[broker.broker_id] = broker
        logger.info(f"Registered broker: {broker.broker_id}")
        
    def get_broker(self, broker_id: str | BrokerID) -> BrokerFacade:
        """Get a specific broker by ID."""
        if isinstance(broker_id, str):
            broker_id = BrokerID.from_string(broker_id)
            
        if broker_id not in self._brokers:
            from inc_trade.domain.exceptions import BrokerError
            raise BrokerError(f"Broker {broker_id} is not registered or active.")
            
        return self._brokers[broker_id]
        
    def has_broker(self, broker_id: BrokerID) -> bool:
        """Check if a broker is currently registered."""
        return broker_id in self._brokers
        
    def get_active_brokers(self) -> dict[BrokerID, BrokerFacade]:
        """Get all currently registered brokers."""
        return self._brokers.copy()
        
    def place_order(self, request: OrderRequest, preferred_broker: BrokerID | None = None) -> OrderResponse:
        """Route and execute an order.
        
        The OMS does not care which broker executes the order. The router
        makes the decision based on availability and capabilities.
        """
        # Let the router pick the best broker
        broker = self._router.route_order(request, preferred_broker=preferred_broker)
        
        # Execute via the unified facade
        return broker.place_order(request=request)
        
    def close_all(self) -> None:
        """Close all active broker connections."""
        for broker in self._brokers.values():
            broker.close()
        self._brokers.clear()

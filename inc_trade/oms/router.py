"""OMS Routing engine — dynamic multi-broker routing."""

from __future__ import annotations

import logging
from typing import Any

from inc_trade.domain.enums import BrokerID
from inc_trade.domain.entities import OrderRequest
from inc_trade.services.broker_facade import BrokerFacade

logger = logging.getLogger(__name__)


class OrderRouter:
    """Intelligently routes orders across multiple brokers based on policies."""
    
    def __init__(self, broker_manager: Any):
        self._manager = broker_manager
        
    def route_order(self, request: OrderRequest, preferred_broker: BrokerID | None = None) -> BrokerFacade:
        """Decide which broker should execute the order.
        
        Args:
            request: The order details
            preferred_broker: Optional override to force a specific broker
            
        Returns:
            The selected BrokerFacade instance
        """
        # If explicitly requested, use that broker (if available)
        if preferred_broker and self._manager.has_broker(preferred_broker):
            return self._manager.get_broker(preferred_broker)
            
        # In a real OMS, this would check:
        # 1. Which broker has sufficient margin for this specific trade
        # 2. Which broker's connection is healthiest (circuit breaker state)
        # 3. Which broker offers the best execution for the specific exchange
        #
        # For now, default to the primary broker (usually Dhan) or the first available
        active_brokers = self._manager.get_active_brokers()
        if not active_brokers:
            from inc_trade.domain.exceptions import BrokerError
            raise BrokerError("No active brokers available for routing")
            
        if BrokerID.DHAN in active_brokers:
            return self._manager.get_broker(BrokerID.DHAN)
            
        return next(iter(active_brokers.values()))

"""Order Management System (OMS) and Multi-Broker Routing.

This layer sits above the individual BrokerFacades and provides centralized
broker management and dynamic order routing.
"""

from inc_trade.oms.idempotency import IdempotencyCache as IdempotencyCache
from inc_trade.oms.kill_switch import KillSwitch as KillSwitch
from inc_trade.oms.manager import OrderManagementSystem as OrderManagementSystem
from inc_trade.oms.router import ExecutionRouter as ExecutionRouter

# Backward compatibility aliases (deprecated)
BrokerManager = OrderManagementSystem
OrderRouter = ExecutionRouter

__all__ = [
    "OrderManagementSystem",
    "ExecutionRouter",
    "KillSwitch",
    "IdempotencyCache",
    # Backward compat
    "BrokerManager",
    "OrderRouter",
]

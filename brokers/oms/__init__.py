"""Order Management System (OMS) and Multi-Broker Routing.

This layer sits above the individual BrokerFacades and provides centralized
broker management and dynamic order routing.
"""

from brokers.oms.manager import BrokerManager as BrokerManager
from brokers.oms.router import OrderRouter as OrderRouter

__all__ = ["BrokerManager", "OrderRouter"]

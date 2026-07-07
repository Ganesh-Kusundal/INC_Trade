"""Dhan extended capabilities — broker-specific features beyond TradingPort/MarketDataPort.

Provides:
- Super/bracket orders
- Forever/GTT orders
- Conditional triggers
- Ledger entries
- User profile
- IP management
- eDIS authorization
- Exit all positions
- Margin calculator
- Price alerts
"""

from __future__ import annotations

from .alerts import Alert, AlertRequest, DhanAlerts
from .conditional_triggers import ConditionalTriggerRequest, DhanConditionalTriggers
from .edis import DhanEdis
from .exit_all import DhanExitAll, ExitAllResult
from .facade import DhanExtended
from .forever_orders import DhanForeverOrders, ForeverOrderRequest
from .ip_management import DhanIpManagement, IpEntry
from .ledger import DhanLedger, LedgerEntry
from .margin import DhanMargin, MarginResult
from .reconciliation import DhanReconciliation
from .super_orders import DhanSuperOrders, SuperOrderRequest
from .user_profile import DhanUserProfile, UserProfile

__all__ = [
    "DhanExtended",
    "DhanAlerts", "Alert", "AlertRequest",
    "DhanConditionalTriggers", "ConditionalTriggerRequest",
    "DhanEdis",
    "DhanExitAll", "ExitAllResult",
    "DhanForeverOrders", "ForeverOrderRequest",
    "DhanIpManagement", "IpEntry",
    "DhanLedger", "LedgerEntry",
    "DhanMargin", "MarginResult",
    "DhanReconciliation",
    "DhanSuperOrders", "SuperOrderRequest",
    "DhanUserProfile", "UserProfile",
]

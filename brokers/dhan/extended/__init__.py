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
- Position conversion
- Kill switch
- Expired options data
- Slice orders
- Order lookup by correlation ID
"""

from __future__ import annotations

from .alerts import Alert, AlertRequest, DhanAlerts
from .conditional_triggers import ConditionalTriggerRequest, DhanConditionalTriggers
from .convert_position import ConvertPositionRequest, ConvertPositionResult, DhanConvertPosition
from .edis import DhanEdis
from .exit_all import DhanExitAll, ExitAllResult
from .expired_options import DhanExpiredOptions, ExpiredOptionsRequest, ExpiredOptionsResult
from .facade import DhanExtended
from .forever_orders import DhanForeverOrders, ForeverOrderRequest
from .ip_management import DhanIpManagement, IpEntry
from .kill_switch import DhanKillSwitch, KillSwitchResult
from .ledger import DhanLedger, LedgerEntry
from .margin import DhanMargin, MarginResult
from .order_lookup import DhanOrderLookup
from .reconciliation import DhanReconciliation
from .slice_order import DhanSliceOrder, SliceOrderRequest, SliceOrderResult
from .super_orders import DhanSuperOrders, SuperOrderRequest
from .user_profile import DhanUserProfile, UserProfile

__all__ = [
    "DhanExtended",
    "DhanAlerts", "Alert", "AlertRequest",
    "DhanConditionalTriggers", "ConditionalTriggerRequest",
    "DhanConvertPosition", "ConvertPositionRequest", "ConvertPositionResult",
    "DhanEdis",
    "DhanExitAll", "ExitAllResult",
    "DhanExpiredOptions", "ExpiredOptionsRequest", "ExpiredOptionsResult",
    "DhanForeverOrders", "ForeverOrderRequest",
    "DhanIpManagement", "IpEntry",
    "DhanKillSwitch", "KillSwitchResult",
    "DhanLedger", "LedgerEntry",
    "DhanMargin", "MarginResult",
    "DhanOrderLookup",
    "DhanReconciliation",
    "DhanSliceOrder", "SliceOrderRequest", "SliceOrderResult",
    "DhanSuperOrders", "SuperOrderRequest",
    "DhanUserProfile", "UserProfile",
]

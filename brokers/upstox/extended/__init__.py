"""Upstox extended capabilities — broker-specific features beyond TradingPort/MarketDataPort.

Provides:
- IPO management, Payments, Mutual funds, Fundamentals, News
- Market intelligence (PCR, max pain, OI, FII/DII)
- Kill switch, Static IP
- GTT orders, Slice orders, Cover orders, Alerts, Exit all
- Market status, Expired instruments, Margin calculator
- Order query, Reconciliation
"""

from __future__ import annotations

from .alerts import UpstoxAlerts
from .cover_order import UpstoxCoverOrders
from .exit_all import UpstoxExitAll
from .expired_instruments import UpstoxExpiredInstruments
from .facade import UpstoxExtended
from .fundamentals import UpstoxFundamentals
from .gtt import UpstoxGTT
from .ipo import UpstoxIPO
from .kill_switch import UpstoxKillSwitch
from .margin import UpstoxMargin
from .market_intelligence import UpstoxMarketIntelligence
from .market_status import UpstoxMarketStatus
from .mutual_funds import UpstoxMutualFunds
from .news import UpstoxNews
from .order_query import UpstoxOrderQuery
from .payments import UpstoxPayments
from .reconciliation import UpstoxReconciliation
from .slice import UpstoxSliceOrders
from .static_ip import UpstoxStaticIp

__all__ = [
    "UpstoxExtended",
    "UpstoxAlerts",
    "UpstoxCoverOrders",
    "UpstoxExitAll",
    "UpstoxExpiredInstruments",
    "UpstoxFundamentals",
    "UpstoxGTT",
    "UpstoxIPO",
    "UpstoxKillSwitch",
    "UpstoxMargin",
    "UpstoxMarketIntelligence",
    "UpstoxMarketStatus",
    "UpstoxMutualFunds",
    "UpstoxNews",
    "UpstoxOrderQuery",
    "UpstoxPayments",
    "UpstoxReconciliation",
    "UpstoxSliceOrders",
    "UpstoxStaticIp",
]

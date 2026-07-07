"""Upstox extended capabilities facade — aggregates all Upstox-specific features.

Provides a single entry point for all Upstox extended capabilities,
accessible via ``adapter.extended`` or ``gateway.extended``.

Usage::

    from brokers.upstox.extended.facade import UpstoxExtended

    ext = UpstoxExtended(client=upstox_client)
    ext.ipo.get_ipos(status="open")
    ext.gtt.place_single(payload)
    ext.market_intelligence.get_pcr()
"""

from __future__ import annotations

from brokers.upstox.client import UpstoxHttpClient

from .alerts import UpstoxAlerts
from .cover_order import UpstoxCoverOrders
from .exit_all import UpstoxExitAll
from .expired_instruments import UpstoxExpiredInstruments
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


class UpstoxExtended:
    """Facade aggregating all Upstox-specific extended capabilities.

    Each capability is exposed as a property that lazily creates the
    underlying adapter on first access.

    Usage::

        ext = UpstoxExtended(client=upstox_client)
        ext.ipo.get_ipos(status="open")
        ext.gtt.place_single(payload)
        ext.market_intelligence.get_pcr()
    """

    def __init__(self, *, client: UpstoxHttpClient) -> None:
        self._client = client
        self._ipo: UpstoxIPO | None = None
        self._payments: UpstoxPayments | None = None
        self._mutual_funds: UpstoxMutualFunds | None = None
        self._fundamentals: UpstoxFundamentals | None = None
        self._news: UpstoxNews | None = None
        self._market_intelligence: UpstoxMarketIntelligence | None = None
        self._kill_switch: UpstoxKillSwitch | None = None
        self._static_ip: UpstoxStaticIp | None = None
        self._gtt: UpstoxGTT | None = None
        self._slice: UpstoxSliceOrders | None = None
        self._cover_order: UpstoxCoverOrders | None = None
        self._alerts: UpstoxAlerts | None = None
        self._exit_all: UpstoxExitAll | None = None
        self._market_status: UpstoxMarketStatus | None = None
        self._expired_instruments: UpstoxExpiredInstruments | None = None
        self._margin: UpstoxMargin | None = None
        self._order_query: UpstoxOrderQuery | None = None
        self._reconciliation: UpstoxReconciliation | None = None

    @property
    def ipo(self) -> UpstoxIPO:
        if self._ipo is None:
            self._ipo = UpstoxIPO(client=self._client)
        return self._ipo

    @property
    def payments(self) -> UpstoxPayments:
        if self._payments is None:
            self._payments = UpstoxPayments(client=self._client)
        return self._payments

    @property
    def mutual_funds(self) -> UpstoxMutualFunds:
        if self._mutual_funds is None:
            self._mutual_funds = UpstoxMutualFunds(client=self._client)
        return self._mutual_funds

    @property
    def fundamentals(self) -> UpstoxFundamentals:
        if self._fundamentals is None:
            self._fundamentals = UpstoxFundamentals(client=self._client)
        return self._fundamentals

    @property
    def news(self) -> UpstoxNews:
        if self._news is None:
            self._news = UpstoxNews(client=self._client)
        return self._news

    @property
    def market_intelligence(self) -> UpstoxMarketIntelligence:
        if self._market_intelligence is None:
            self._market_intelligence = UpstoxMarketIntelligence(client=self._client)
        return self._market_intelligence

    @property
    def kill_switch(self) -> UpstoxKillSwitch:
        if self._kill_switch is None:
            self._kill_switch = UpstoxKillSwitch(client=self._client)
        return self._kill_switch

    @property
    def static_ip(self) -> UpstoxStaticIp:
        if self._static_ip is None:
            self._static_ip = UpstoxStaticIp(client=self._client)
        return self._static_ip

    @property
    def gtt(self) -> UpstoxGTT:
        if self._gtt is None:
            self._gtt = UpstoxGTT(client=self._client)
        return self._gtt

    @property
    def slice(self) -> UpstoxSliceOrders:
        if self._slice is None:
            self._slice = UpstoxSliceOrders(client=self._client)
        return self._slice

    @property
    def cover_order(self) -> UpstoxCoverOrders:
        if self._cover_order is None:
            self._cover_order = UpstoxCoverOrders(client=self._client)
        return self._cover_order

    @property
    def alerts(self) -> UpstoxAlerts:
        if self._alerts is None:
            self._alerts = UpstoxAlerts(client=self._client)
        return self._alerts

    @property
    def exit_all(self) -> UpstoxExitAll:
        if self._exit_all is None:
            self._exit_all = UpstoxExitAll(client=self._client)
        return self._exit_all

    @property
    def market_status(self) -> UpstoxMarketStatus:
        if self._market_status is None:
            self._market_status = UpstoxMarketStatus(client=self._client)
        return self._market_status

    @property
    def expired_instruments(self) -> UpstoxExpiredInstruments:
        if self._expired_instruments is None:
            self._expired_instruments = UpstoxExpiredInstruments(client=self._client)
        return self._expired_instruments

    @property
    def margin(self) -> UpstoxMargin:
        if self._margin is None:
            self._margin = UpstoxMargin(client=self._client)
        return self._margin

    @property
    def order_query(self) -> UpstoxOrderQuery:
        if self._order_query is None:
            self._order_query = UpstoxOrderQuery(client=self._client)
        return self._order_query

    @property
    def reconciliation(self) -> UpstoxReconciliation:
        if self._reconciliation is None:
            self._reconciliation = UpstoxReconciliation(client=self._client)
        return self._reconciliation


__all__ = ["UpstoxExtended"]

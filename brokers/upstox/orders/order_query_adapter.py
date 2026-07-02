"""Upstox order query adapter — implements ``OrderQuery`` port."""

from __future__ import annotations

from brokers.common.gateway_interfaces import OrderQuery
from brokers.upstox.instruments.resolver import UpstoxInstrumentResolver
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper
from brokers.upstox.orders.order_client import UpstoxRestOrderClient
from domain import Order, Trade


class UpstoxOrderQueryAdapter(OrderQuery):
    def __init__(
        self,
        order_client: UpstoxRestOrderClient,
        instrument_resolver: UpstoxInstrumentResolver,
    ) -> None:
        self._order_client = order_client
        self._instrument_resolver = instrument_resolver

    def get_order(self, order_id: str) -> Order | None:
        body = self._order_client.get_order(order_id)
        if not isinstance(body, dict):
            return None
        data = body.get("data")
        if isinstance(data, list):
            if not data:
                return None
            return UpstoxDomainMapper.to_order(data[0])
        if isinstance(data, dict):
            return UpstoxDomainMapper.to_order(data)
        return None

    def get_order_by_correlation_id(self, correlation_id: str) -> Order | None:
        for row in self._order_client.get_order_list():
            if isinstance(row, dict) and row.get("tag") == correlation_id:
                return UpstoxDomainMapper.to_order(row)
        return None

    def get_order_list(self) -> list[Order]:
        return [
            UpstoxDomainMapper.to_order(r)
            for r in self._order_client.get_order_list()
            if isinstance(r, dict)
        ]

    def get_trades(self) -> list[Trade]:
        return [
            UpstoxDomainMapper.to_trade(r)
            for r in self._order_client.get_trades_for_day()
            if isinstance(r, dict)
        ]

    def get_trades_for_order(self, order_id: str) -> list[Trade]:
        trades = self._order_client.get_trades_by_order(order_id)
        return [UpstoxDomainMapper.to_trade(t) for t in trades if isinstance(t, dict)]

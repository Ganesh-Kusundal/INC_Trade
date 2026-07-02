"""Dhan gateway — composes all Dhan adapters into BrokerGateway."""

from __future__ import annotations

from brokers.adapters.dhan.auth import DhanAuth
from brokers.adapters.dhan.historical import DhanHistorical
from brokers.adapters.dhan.http import DhanHttpClient
from brokers.adapters.dhan.identity import DhanInstrumentResolver
from brokers.adapters.dhan.instruments import DhanInstruments
from brokers.adapters.dhan.market_data import DhanMarketData
from brokers.adapters.dhan.orders import DhanOrders
from brokers.adapters.dhan.portfolio import DhanPortfolio
from brokers.adapters.dhan.streaming import DhanStreaming


class DhanGateway:
    """Dhan broker adapter implementing BrokerGateway protocol.

    Args:
        access_token: Dhan API access token.
        client_id: Dhan client ID.
    """

    def __init__(self, access_token: str, client_id: str):
        self._client = DhanHttpClient(access_token=access_token, client_id=client_id)
        self._resolver = DhanInstrumentResolver()
        self._orders = DhanOrders(self._client, self._resolver)
        self._market_data = DhanMarketData(self._client, self._resolver)
        self._portfolio = DhanPortfolio(self._client)
        self._instruments = DhanInstruments(self._resolver)
        self._auth = DhanAuth(access_token, client_id)
        self._historical = DhanHistorical(self._client, self._resolver)
        self._streaming = DhanStreaming(access_token=access_token, client_id=client_id)

    @property
    def orders(self) -> DhanOrders:
        return self._orders

    @property
    def market_data(self) -> DhanMarketData:
        return self._market_data

    @property
    def portfolio(self) -> DhanPortfolio:
        return self._portfolio

    @property
    def instruments(self) -> DhanInstruments:
        return self._instruments

    @property
    def auth(self) -> DhanAuth:
        return self._auth

    @property
    def historical(self) -> DhanHistorical:
        return self._historical

    @property
    def streaming(self) -> DhanStreaming:
        return self._streaming

    def close(self) -> None:
        self._streaming.stop()
        self._client.close()

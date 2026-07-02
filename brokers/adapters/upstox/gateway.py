"""Upstox gateway — composes all Upstox adapters into BrokerGateway."""

from __future__ import annotations

from brokers.adapters.upstox.auth import UpstoxAuth
from brokers.adapters.upstox.historical import UpstoxHistorical
from brokers.adapters.upstox.http import UpstoxHttpClient
from brokers.adapters.upstox.instruments import UpstoxInstruments
from brokers.adapters.upstox.market_data import UpstoxMarketData
from brokers.adapters.upstox.orders import UpstoxOrders
from brokers.adapters.upstox.portfolio import UpstoxPortfolio
from brokers.adapters.upstox.streaming import UpstoxStreaming


class UpstoxGateway:
    """Upstox broker adapter implementing BrokerGateway protocol.

    Args:
        access_token: Upstox API access token (Bearer token from OAuth flow).
    """

    def __init__(self, access_token: str, allow_live_orders: bool = True):
        self._client = UpstoxHttpClient(access_token=access_token)
        self._orders = UpstoxOrders(self._client, allow_live_orders=allow_live_orders)
        self._market_data = UpstoxMarketData(self._client)
        self._portfolio = UpstoxPortfolio(self._client)
        self._instruments = UpstoxInstruments()
        self._auth = UpstoxAuth(access_token)
        self._historical = UpstoxHistorical(self._client)
        self._streaming = UpstoxStreaming(access_token=access_token)

    @property
    def orders(self) -> UpstoxOrders:
        return self._orders

    @property
    def market_data(self) -> UpstoxMarketData:
        return self._market_data

    @property
    def portfolio(self) -> UpstoxPortfolio:
        return self._portfolio

    @property
    def instruments(self) -> UpstoxInstruments:
        return self._instruments

    @property
    def auth(self) -> UpstoxAuth:
        return self._auth

    @property
    def historical(self) -> UpstoxHistorical:
        return self._historical

    @property
    def streaming(self) -> UpstoxStreaming:
        return self._streaming

    def close(self) -> None:
        self._streaming.stop()
        self._client.close()

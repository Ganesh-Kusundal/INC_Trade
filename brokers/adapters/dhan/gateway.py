"""Dhan gateway — composes all Dhan adapters into BrokerGateway."""

from __future__ import annotations

from brokers.adapters.dhan.auth import DhanAuth
from brokers.adapters.dhan.extensions.forever_orders import DhanForeverOrders
from brokers.adapters.dhan.extensions.margin import DhanMargin
from brokers.adapters.dhan.extensions.super_orders import DhanSuperOrders
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
        pin: PIN for TOTP login.
        totp_secret: Secret for TOTP login.
    """

    def __init__(
        self,
        access_token: str | None = None,
        client_id: str | None = None,
        pin: str | None = None,
        totp_secret: str | None = None,
    ):
        self._auth = DhanAuth(
            access_token=access_token,
            client_id=client_id,
            pin=pin,
            totp_secret=totp_secret,
        )
        token = self._auth.get_token()
        self._client = DhanHttpClient(access_token=token, client_id=client_id or "")
        self._resolver = DhanInstrumentResolver()
        self._orders = DhanOrders(self._client, self._resolver)
        self._market_data = DhanMarketData(self._client, self._resolver)
        self._portfolio = DhanPortfolio(self._client)
        self._instruments = DhanInstruments(self._resolver)
        self._historical = DhanHistorical(self._client, self._resolver)
        self._super_orders = DhanSuperOrders(self._client, self._resolver)
        self._forever_orders = DhanForeverOrders(self._client, self._resolver)
        self._margin = DhanMargin(self._client, self._resolver)
        self._streaming = DhanStreaming(access_token=token, client_id=client_id or "")

    @property
    def orders(self) -> DhanOrders:
        return self._orders

    @property
    def super_orders(self) -> DhanSuperOrders:
        return self._super_orders

    @property
    def forever_orders(self) -> DhanForeverOrders:
        return self._forever_orders

    @property
    def margin(self) -> DhanMargin:
        return self._margin

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


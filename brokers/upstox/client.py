"""Upstox HTTP client — broker-specific endpoints built on BaseHttpClient.

Auth: ``Authorization: Bearer {access_token}`` header
Base URL: ``https://api.upstox.com``
Rate limits: Per-endpoint (orders=10/s, standard APIs=50/s)

Usage::

    from brokers.upstox.client import UpstoxHttpClient

    client = UpstoxHttpClient(access_token="tok")
    data = client.get("/v3/order/retrieve-all")
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from brokers.constants import DEFAULT_HTTP_MAX_RETRIES, DEFAULT_HTTP_TIMEOUT
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.rate_config import upstox_rate_config

UPSTOX_BASE_URL = "https://api.upstox.com"


class UpstoxHttpClient(BaseHttpClient):
    """Upstox REST API client with Bearer auth and per-endpoint rate limiting."""

    def __init__(
        self,
        *,
        access_token: str,
        base_url: str = UPSTOX_BASE_URL,
        timeout: float = DEFAULT_HTTP_TIMEOUT,
        token_refresh_fn: Callable[[], str | None] | None = None,
        max_retries: int = DEFAULT_HTTP_MAX_RETRIES,
    ) -> None:
        super().__init__(
            base_url=base_url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}",
            },
            rate_config=upstox_rate_config(),
            timeout=timeout,
            token_refresh_fn=token_refresh_fn,
            token_header_key="Authorization",
            max_retries=max_retries,
        )

    def update_token(self, token: str) -> None:
        """Update the Bearer token in the Authorization header."""
        self._session.headers[self._token_header_key] = f"Bearer {token}"

    # ── Order endpoints ─────────────────────────────────────────────────────

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /v3/order/place — place a new order."""
        return self.post("/v3/order/place", json=payload)

    def modify_order(self, order_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """PUT /v3/order/modify — modify an existing order."""
        payload = {"order_id": order_id, **changes}
        return self.put("/v3/order/modify", json=payload)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """DELETE /v3/order/cancel — cancel an order."""
        return self.delete(f"/v3/order/cancel?order_id={order_id}")

    def get_order(self, order_id: str) -> dict[str, Any]:
        """GET /v3/order/history — get order history (includes status)."""
        return self.get(f"/v3/order/history?order_id={order_id}")

    def get_orderbook(self) -> dict[str, Any]:
        """GET /v3/order/retrieve-all — fetch all orders."""
        return self.get("/v3/order/retrieve-all")

    def get_trades(self) -> dict[str, Any]:
        """GET /v3/trades/trades-for-day — fetch today's trades."""
        return self.get("/v3/trades/trades-for-day")

    def get_historical_trades(
        self, instrument_key: str, from_date: str, to_date: str
    ) -> dict[str, Any]:
        """GET /v3/trades/historical — fetch historical trades."""
        return self.get(
            f"/v3/trades/historical?instrument_key={instrument_key}&from_date={from_date}&to_date={to_date}"
        )

    # ── Market data endpoints ───────────────────────────────────────────────

    def get_ltp(self, instrument_keys: list[str]) -> dict[str, Any]:
        """GET /v3/market-quote/ltp — get last traded price."""
        keys = ",".join(instrument_keys)
        return self.get(f"/v3/market-quote/ltp?instrument_key={keys}")

    def get_quote(self, instrument_keys: list[str]) -> dict[str, Any]:
        """GET /v3/market-quote/quotes — get full quote."""
        keys = ",".join(instrument_keys)
        return self.get(f"/v3/market-quote/quotes?instrument_key={keys}")

    def get_ohlc(self, instrument_keys: list[str]) -> dict[str, Any]:
        """GET /v3/market-quote/ohlc — get OHLC data."""
        keys = ",".join(instrument_keys)
        return self.get(f"/v3/market-quote/ohlc?instrument_key={keys}")

    def get_option_chain(self, underlying: str, expiry: str) -> dict[str, Any]:
        """GET /v2/option/chain — get option chain."""
        return self.get(f"/v2/option/chain?instrument_key={underlying}&expiry_date={expiry}")

    def get_historical_candles(
        self, instrument_key: str, interval: str, from_date: str, to_date: str
    ) -> dict[str, Any]:
        """GET /v2/historical-candle/{instrument_key}/{interval}/{from}/{to}"""
        return self.get(
            f"/v2/historical-candle/{instrument_key}/{interval}/{from_date}/{to_date}"
        )

    # ── Portfolio endpoints ─────────────────────────────────────────────────

    def get_positions(self) -> dict[str, Any]:
        """GET /v2/portfolio/short-term-positions — fetch open positions."""
        return self.get("/v2/portfolio/short-term-positions")

    def get_holdings(self) -> dict[str, Any]:
        """GET /v2/portfolio/long-term-holdings — fetch long-term holdings."""
        return self.get("/v2/portfolio/long-term-holdings")

    def get_funds(self) -> dict[str, Any]:
        """GET /v2/user/get-fund-and-margin — fetch fund limits."""
        return self.get("/v2/user/get-fund-and-margin")


__all__ = ["UpstoxHttpClient", "UPSTOX_BASE_URL"]

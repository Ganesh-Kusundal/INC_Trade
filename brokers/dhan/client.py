"""Dhan HTTP client — broker-specific endpoints built on BaseHttpClient.

Auth: ``access-token`` + ``client-id`` headers
Base URL: ``https://api.dhan.co/v2``
Rate limits: Per-endpoint (quote=1/s, data=10/s, orders=25/s)

Usage::

    from brokers.dhan.client import DhanHttpClient

    client = DhanHttpClient(client_id="123", access_token="tok")
    data = client.post("/orders", json={...})
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from brokers.constants import DEFAULT_HTTP_MAX_RETRIES, DEFAULT_HTTP_TIMEOUT
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.rate_config import dhan_rate_config

DHAN_BASE_URL = "https://api.dhan.co/v2"


class DhanHttpClient(BaseHttpClient):
    """Dhan REST API client with per-endpoint rate limiting and circuit breakers."""

    def __init__(
        self,
        *,
        client_id: str,
        access_token: str,
        base_url: str = DHAN_BASE_URL,
        timeout: float = DEFAULT_HTTP_TIMEOUT,
        token_refresh_fn: Callable[[], str | None] | None = None,
        max_retries: int = DEFAULT_HTTP_MAX_RETRIES,
    ) -> None:
        super().__init__(
            base_url=base_url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "client-id": client_id,
                "access-token": access_token,
            },
            rate_config=dhan_rate_config(),
            timeout=timeout,
            token_refresh_fn=token_refresh_fn,
            token_header_key="access-token",
            max_retries=max_retries,
        )
        self.client_id = client_id

    # ── Order endpoints ─────────────────────────────────────────────────────

    def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /orders — place a new order."""
        return self.post("/orders", json=payload)

    def modify_order(self, order_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """PUT /orders/{order_id} — modify an existing order."""
        return self.put(f"/orders/{order_id}", json=changes)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """DELETE /orders/{order_id} — cancel an order."""
        return self.delete(f"/orders/{order_id}")

    def get_order(self, order_id: str) -> dict[str, Any]:
        """GET /orders/{order_id} — fetch a single order."""
        return self.get(f"/orders/{order_id}")

    def get_orderbook(self) -> dict[str, Any]:
        """GET /orders — fetch all orders."""
        return self.get("/orders")

    def get_trades(self) -> dict[str, Any]:
        """GET /trades — fetch today's trade book."""
        return self.get("/trades")

    def get_trade_history(
        self, from_date: str, to_date: str
    ) -> dict[str, Any]:
        """POST /trades — fetch trade history for a date range.

        Args:
            from_date: Start date in ``YYYY-MM-DD`` format.
            to_date: End date in ``YYYY-MM-DD`` format.
        """
        return self.post(
            "/trades",
            json={"fromDate": from_date, "toDate": to_date},
        )

    # ── Market data endpoints ───────────────────────────────────────────────

    def get_ltp(self, segment: str, security_ids: list[int]) -> dict[str, Any]:
        """POST /marketfeed/ltp — get last traded price."""
        return self.post("/marketfeed/ltp", json={segment: security_ids})

    def get_quote(self, segment: str, security_ids: list[int]) -> dict[str, Any]:
        """POST /marketfeed/quote — get full quote."""
        return self.post("/marketfeed/quote", json={segment: security_ids})

    def get_ohlc(self, segment: str, security_ids: list[int]) -> dict[str, Any]:
        """POST /marketfeed/ohlc — get OHLC data."""
        return self.post("/marketfeed/ohlc", json={segment: security_ids})

    def get_option_chain(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /optionchain — get option chain."""
        return self.post("/optionchain", json=payload)

    def get_historical(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /charts/historical — daily historical candles."""
        return self.post("/charts/historical", json=payload)

    def get_intraday(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /charts/intraday — intraday candles."""
        return self.post("/charts/intraday", json=payload)

    def update_access_token(self, new_token: str) -> None:
        """Hot-swap the access token in session headers.

        Called by :class:`DhanTokenScheduler` when it refreshes the
        token — keeps the HTTP client in sync without reconnecting.

        Thread-safe: dict key assignment is atomic under the GIL.
        """
        self._session.headers["access-token"] = new_token

    # ── Portfolio endpoints ─────────────────────────────────────────────────

    def get_positions(self) -> dict[str, Any]:
        """GET /positions — fetch open positions."""
        return self.get("/positions")

    def get_holdings(self) -> dict[str, Any]:
        """GET /holdings — fetch long-term holdings."""
        return self.get("/holdings")

    def get_funds(self) -> dict[str, Any]:
        """GET /fundlimit — fetch fund limits and balance."""
        return self.get("/fundlimit")


__all__ = ["DhanHttpClient", "DHAN_BASE_URL"]

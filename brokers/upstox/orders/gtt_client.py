"""Upstox GTT (Good Till Triggered) order client (V3 HFT, with TSL support).

Mirrors Trade_J ``UpstoxGttRestClient``.
"""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxGttClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def place_gtt_single(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.post_json(self._urls.gtt_place_url(), payload)

    def place_gtt_multi(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.post_json(self._urls.gtt_place_url(), payload)

    def modify_gtt(self, gtt_order_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.put_json(self._urls.gtt_modify_url() + f"/{gtt_order_id}", payload)

    def cancel_gtt(self, gtt_order_id: str) -> dict[str, Any]:
        return self._http.delete_json(self._urls.gtt_cancel_url() + f"/{gtt_order_id}")

    def get_gtt_orders(self, gtt_order_id: str) -> dict[str, Any]:
        return self._http.get_json(
            self._urls.gtt_orders_url(),
            params={"gtt_order_id": gtt_order_id},
        )

    def get_gtt_order_details(self, gtt_order_id: str) -> dict[str, Any]:
        return self._http.get_json(self._urls.gtt_order_details_url() + f"/{gtt_order_id}")

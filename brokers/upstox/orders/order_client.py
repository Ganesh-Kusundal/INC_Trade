"""Upstox REST order client (V2 + V3 HFT).

Mirrors Trade_J ``UpstoxOrderRestClient``. V3 endpoints are used by default; V2
fallback is available for legacy callers.
"""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver
from brokers.upstox.mappers.domain_mapper import UpstoxDomainMapper


class UpstoxRestOrderClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def place_order_v3(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.post_json(self._urls.place_order_v3_url(), payload)

    def place_order_v2(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.post_json(self._urls.place_order_v2_url(), payload)

    def modify_order_v3(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.put_json(self._urls.modify_order_v3_url(), payload)

    def cancel_order_v3(self, order_id: str) -> dict[str, Any]:
        return self._http.delete_json(
            self._urls.cancel_order_v3_url(), params={"order_id": order_id}
        )

    def get_order(self, order_id: str) -> dict[str, Any]:
        return self._http.get_json(self._urls.order_details_url(), params={"order_id": order_id})

    def get_order_list(self) -> list[dict[str, Any]]:
        body = self._http.get_json(self._urls.order_book_url())
        return _data_list(body)

    def get_trades_for_day(self) -> list[dict[str, Any]]:
        """Get today's executed trades from the dedicated trades endpoint."""
        body = self._http.get_json(self._urls.trades_for_day_url())
        return _data_list(body)

    def get_trades_by_order(self, order_id: str) -> list[dict[str, Any]]:
        """Get trades for a specific order."""
        body = self._http.get_json(
            self._urls.trades_for_day_url(), params={"order_id": order_id}
        )
        return _data_list(body)

    def get_order_history(self, order_id: str) -> list[dict[str, Any]]:
        body = self._http.get_json(
            self._urls.order_history_url(), params={"order_id": order_id}
        )
        return _data_list(body)

    def place_multi_order(self, payloads: list[dict[str, Any]]) -> dict[str, Any]:
        return self._http.post_json(self._urls.multi_order_v2_url(), payloads)

    def cancel_multi_order(self, order_ids: list[str]) -> dict[str, Any]:
        return self._http.delete_json(
            self._urls.cancel_order_v3_url(), payload={"order_ids": order_ids}
        )

    def convert_position(
        self,
        instrument_key: str,
        transaction_type: str,
        product_from: str,
        product_to: str,
        quantity: int,
    ) -> dict[str, Any]:
        payload = {
            "instrument_token": instrument_key,
            "transaction_type": transaction_type,
            "product_from": product_from,
            "product_to": product_to,
            "quantity": quantity,
        }
        return self._http.put_json(self._urls.convert_position_url(), payload)

    def build_place_payload(
        self, request: Any, instrument_key: str, **kwargs: Any
    ) -> dict[str, Any]:
        return UpstoxDomainMapper.to_place_payload(request, instrument_key, **kwargs)


def _data_list(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    data = body.get("data")
    return data if isinstance(data, list) else []

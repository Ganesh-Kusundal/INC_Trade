"""Upstox payments REST client (payouts)."""

from __future__ import annotations

from typing import Any

from brokers.upstox.auth.urls import UpstoxApiUrlResolver


class UpstoxPaymentsClient:
    def __init__(self, http_client: Any, url_resolver: UpstoxApiUrlResolver) -> None:
        self._http = http_client
        self._urls = url_resolver

    def initiate_payout(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.post_json(self._urls.payouts_url(), payload)

    def get_payouts(self) -> list[dict[str, Any]]:
        body = self._http.get_json(self._urls.payouts_url())
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            data = body.get("data")
            return data if isinstance(data, list) else []
        return []

    def modify_payout(self, payout_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._http.put_json(self._urls.payouts_url() + f"/{payout_id}", payload)

    def cancel_payout(self, payout_id: str) -> dict[str, Any]:
        return self._http.delete_json(self._urls.payouts_url() + f"/{payout_id}")

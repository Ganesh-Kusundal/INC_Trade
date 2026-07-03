"""Upstox GTT (Good Till Triggered) order adapter."""

from __future__ import annotations

from typing import Any

from brokers.adapters.upstox.http import UpstoxHttpClient
from brokers.adapters.upstox.urls import resolve_upstox_urls
from brokers.domain import OrderResponse


class UpstoxGtt:
    def __init__(
        self, client: UpstoxHttpClient, *, environment: str = "LIVE"
    ) -> None:
        self._client = client
        self._urls = resolve_upstox_urls(environment)

    def place_gtt(self, payload: dict[str, Any]) -> OrderResponse:
        data = self._client.post(self._urls.gtt_place_url(), json=payload)
        order_id = ""
        if isinstance(data, dict):
            inner = data.get("data", {})
            if isinstance(inner, dict):
                order_id = str(inner.get("gtt_order_id", inner.get("order_id", "")))
        return OrderResponse(
            order_id=order_id,
            success=bool(order_id),
            message=str(data.get("message", "")) if isinstance(data, dict) else "",
        )

    def _is_success(self, data: Any) -> bool:
        return isinstance(data, dict) and str(data.get("status", "")).lower() in ("success", "ok")

    def modify_gtt(self, gtt_order_id: str, payload: dict[str, Any]) -> OrderResponse:
        data = self._client.put(
            self._urls.gtt_modify_url() + f"/{gtt_order_id}",
            json=payload,
        )
        return OrderResponse(order_id=gtt_order_id, success=self._is_success(data))

    def cancel_gtt(self, gtt_order_id: str) -> OrderResponse:
        data = self._client.delete(
            self._urls.gtt_cancel_url() + f"/{gtt_order_id}"
        )
        return OrderResponse(order_id=gtt_order_id, success=self._is_success(data))

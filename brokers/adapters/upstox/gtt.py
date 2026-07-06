"""Upstox GTT (Good Till Triggered) order adapter."""

from __future__ import annotations

from typing import Any

from inc_trade.domain import OrderResponse
from inc_trade.ports.http_client_port import HttpClientPort

from brokers.adapters.upstox.urls import resolve_upstox_urls


class UpstoxGtt:
    def __init__(self, client: HttpClientPort, *, environment: str = "LIVE") -> None:
        self._client = client
        self._urls = resolve_upstox_urls(environment)

    def place_gtt(self, request: dict[str, Any]) -> OrderResponse:
        data = self._client.post(self._urls.gtt_place_url(), json=request)
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

    def modify_gtt(self, gtt_id: str, changes: dict[str, Any]) -> OrderResponse:
        data = self._client.put(
            self._urls.gtt_modify_url() + f"/{gtt_id}",
            json=changes,
        )
        return OrderResponse(order_id=gtt_id, success=self._is_success(data))

    def cancel_gtt(self, gtt_id: str) -> OrderResponse:
        data = self._client.delete(self._urls.gtt_cancel_url() + f"/{gtt_id}")
        return OrderResponse(order_id=gtt_id, success=self._is_success(data))

    def get_gtt_orders(self) -> list[Any]:
        data = self._client.get(self._urls.gtt_place_url())
        if isinstance(data, dict):
            return data.get("data", [])
        return []

"""Upstox extended broker-specific REST APIs."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from inc_trade.domain.entities import IpoInfo, MutualFundHolding, UserProfile
from inc_trade.ports.http_client_port import HttpClientPort

from brokers.adapters.upstox.urls import resolve_upstox_urls


def _parse_user_profile(raw: dict[str, Any]) -> UserProfile:
    return UserProfile(
        user_id=str(raw.get("user_id", "")),
        name=str(raw.get("name", "")),
        email=str(raw.get("email", "")),
        mobile=str(raw.get("mobile", "")),
        broker=str(raw.get("broker", "")),
    )


def _parse_ipo(raw: dict[str, Any]) -> IpoInfo:
    return IpoInfo(
        company_name=str(raw.get("company_name", "")),
        symbol=str(raw.get("symbol", "")),
        status=str(raw.get("status", "")),
        price_min=Decimal(str(raw.get("price_min", "0") or "0")),
        price_max=Decimal(str(raw.get("price_max", "0") or "0")),
    )


def _parse_mf_holding(raw: dict[str, Any]) -> MutualFundHolding:
    return MutualFundHolding(
        name=str(raw.get("name", "")),
        units=Decimal(str(raw.get("units", "0") or "0")),
        current_value=Decimal(str(raw.get("current_value", "0") or "0")),
    )


class UpstoxExtended:
    def __init__(self, client: HttpClientPort, *, environment: str = "LIVE") -> None:
        self._client = client
        self._urls = resolve_upstox_urls(environment)

    def get_user_profile(self) -> UserProfile:
        data = self._client.get(self._urls.profile_url())
        raw = data.get("data", data) if isinstance(data, dict) else data
        return _parse_user_profile(raw if isinstance(raw, dict) else {})

    def get_ipos(self, status: str = "open") -> list[IpoInfo]:
        data = self._client.get(self._urls.ipo_url(), params={"status": status})
        items = data.get("data", []) if isinstance(data, dict) else []
        if not isinstance(items, list):
            items = []
        return [_parse_ipo(item) for item in items if isinstance(item, dict)]

    def get_mutual_fund_holdings(self) -> list[MutualFundHolding]:
        data = self._client.get(self._urls.mutual_funds_holdings_url())
        items = data.get("data", []) if isinstance(data, dict) else []
        if not isinstance(items, list):
            items = []
        return [_parse_mf_holding(item) for item in items if isinstance(item, dict)]

    def convert_position(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.post(self._urls.convert_position_url(), json=payload)

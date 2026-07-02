"""Upstox payments adapter."""

from __future__ import annotations

from typing import Any

from brokers.upstox.payments.client import UpstoxPaymentsClient


class UpstoxPaymentsAdapter:
    def __init__(self, client: UpstoxPaymentsClient) -> None:
        self._client = client

    def initiate_payout(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.initiate_payout(payload)

    def get_payouts(self) -> list[dict[str, Any]]:
        return self._client.get_payouts()

    def modify_payout(self, payout_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._client.modify_payout(payout_id, payload)

    def cancel_payout(self, payout_id: str) -> dict[str, Any]:
        return self._client.cancel_payout(payout_id)

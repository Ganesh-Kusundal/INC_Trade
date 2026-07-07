"""Upstox payments — initiate and manage payouts.

API: POST /v2/payment/initiate — initiate payout
     GET /v2/payment/status — get payout status
     PUT /v2/payment/modify — modify payout
     DELETE /v2/payment/cancel — cancel payout
"""
from __future__ import annotations
from typing import Any
from brokers.infrastructure.http_client import BaseHttpClient
from brokers.infrastructure.logging import get_logger
logger = get_logger(__name__)


class UpstoxPayments:
    """Payment management for Upstox."""

    def __init__(self, *, client: BaseHttpClient) -> None:
        self._client = client

    def initiate_payout(self, amount: float, bank_account_id: str = "") -> dict[str, Any]:
        payload: dict[str, Any] = {"amount": amount}
        if bank_account_id:
            payload["bankAccountId"] = bank_account_id
        logger.info("upstox_payout_initiate", amount=amount)
        return self._client.post("/v2/payment/initiate", json=payload)

    def get_payouts(self) -> list[dict[str, Any]]:
        data = self._client.get("/v2/payment/status")
        result = data.get("data", data) if isinstance(data, dict) else data
        return result if isinstance(result, list) else []

    def modify_payout(self, payout_id: str, amount: float) -> dict[str, Any]:
        return self._client.put("/v2/payment/modify", json={"payoutId": payout_id, "amount": amount})

    def cancel_payout(self, payout_id: str) -> dict[str, Any]:
        return self._client.delete(f"/v2/payment/cancel/{payout_id}")


__all__ = ["UpstoxPayments"]

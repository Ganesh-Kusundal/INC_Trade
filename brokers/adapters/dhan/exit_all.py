"""Dhan Exit All adapter — Panic button to close positions."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from brokers.ports.http_client_port import HttpClientPort

from brokers.adapters.dhan.config import ENDPOINTS

logger = logging.getLogger(__name__)


class DhanExitAll:
    """Adapter for Dhan's Exit All (panic button) functionality.

    Allows instantly closing all open positions or cancelling all open orders.
    """

    def __init__(self, client: HttpClientPort) -> None:
        self._client = client

    def close_all_positions(self) -> dict:
        """Instantly square off all open positions concurrently."""
        logger.warning("executing_exit_all_positions_panic_button")

        data = self._client.get(ENDPOINTS.get("positions", "/positions"))
        positions = data if isinstance(data, list) else data.get("data", [])

        square_off_payloads = []
        for pos in positions:
            net_qty = pos.get("buyQty", 0) - pos.get("sellQty", 0)
            if net_qty == 0:
                continue

            side = 2 if net_qty > 0 else 1  # SELL if long, BUY if short
            payload = {
                "dhanClientId": self._client.client_id,
                "transactionType": side,
                "exchangeSegment": pos.get("exchangeSegment"),
                "securityId": pos.get("securityId"),
                "quantity": abs(net_qty),
                "orderType": 1,  # MARKET
                "productType": pos.get("productType", "INTRADAY"),
                "validity": "DAY",
                "price": 0.0,
                "triggerPrice": 0.0,
            }
            square_off_payloads.append(payload)

        results = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_payload = {
                executor.submit(self._client.post, ENDPOINTS.get("orders", "/orders"), json=p): p
                for p in square_off_payloads
            }
            for future in as_completed(future_to_payload):
                try:
                    res = future.result()
                    results.append(res)
                except Exception as e:
                    logger.error(f"Error squaring off position: {e}")
                    results.append({"status": "error", "error": str(e)})

        return {"squared_off": len(results), "results": results}

    def cancel_all_orders(self) -> dict:
        """Instantly cancel all pending orders concurrently."""
        logger.warning("executing_cancel_all_orders_panic_button")

        data = self._client.get(ENDPOINTS.get("orderbook", "/orders"))
        orders = (
            data.get("data", [])
            if isinstance(data, dict)
            else (data if isinstance(data, list) else [])
        )

        cancel_futures = []
        active_statuses = {"PENDING", "TRANSIT", "OPEN", "PARTIALLY_FILLED"}
        with ThreadPoolExecutor(max_workers=10) as executor:
            for order in orders:
                if order.get("orderStatus") in active_statuses:
                    order_id = order.get("orderId")
                    if order_id:
                        endpoint = ENDPOINTS.get("cancel_order", "/orders/{order_id}").format(
                            order_id=order_id
                        )
                        cancel_futures.append(executor.submit(self._client.post, endpoint))

            results = []
            for future in as_completed(cancel_futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error(f"Error cancelling order: {e}")
                    results.append({"status": "error", "error": str(e)})

        return {"cancelled": len(results), "results": results}

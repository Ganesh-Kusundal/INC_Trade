"""Upstox GTT adapter — implements ``GttOrderProvider`` port.

Mirrors Trade_J ``UpstoxGttOrderAdapter`` + ``UpstoxConditionalAlertProvider``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from brokers.common.gateway_interfaces import GttOrderProvider
from brokers.upstox.orders.gtt_client import UpstoxGttClient
from domain import (
    ConditionalAlert,
    ConditionalAlertRequest,
    Order,
)
from domain.utils.price import to_wire_float


class UpstoxGttAdapter(GttOrderProvider):
    def __init__(self, client: UpstoxGttClient) -> None:
        self._client = client

    def place_gtt_single(
        self,
        request: Order,
        order_flag: str,
        quantity2: int | None = None,
        price2: Decimal | None = None,
        trigger_price2: Decimal | None = None,
    ) -> Order:
        rules: list[dict[str, Any]] = [
            {
                "strategy": "ENTRY",
                "trigger_type": order_flag,
                "trigger_price": to_wire_float(request.price or 0),
            }
        ]
        if quantity2 is not None and price2 is not None and trigger_price2 is not None:
            rules.append(
                {
                    "strategy": "TARGET" if order_flag == "ABOVE" else "STOPLOSS",
                    "trigger_type": "IMMEDIATE",
                    "trigger_price": to_wire_float(trigger_price2),
                    "quantity": int(quantity2),
                    "price": to_wire_float(price2),
                }
            )
        payload = {
            "type": "SINGLE",
            "instrument_token": request.symbol,
            "quantity": request.quantity,
            "product": getattr(request, "product_type", "I"),
            "transaction_type": request.transaction_type.value
            if hasattr(request.transaction_type, "value")
            else str(request.transaction_type),
            "rules": rules,
        }
        body = self._client.place_gtt_single(payload)
        order_id = ""
        if isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, dict):
                order_id = str(data.get("gtt_order_id") or data.get("order_id") or "")
        request.order_id = order_id or "GTT_PENDING"
        return request

    def place_forever_order(
        self,
        request: Order,
        order_flag: str,
        quantity2: int | None = None,
        price2: Decimal | None = None,
        trigger_price2: Decimal | None = None,
    ) -> Order:
        return self.place_gtt_single(request, order_flag, quantity2, price2, trigger_price2)

    def modify_forever_order(
        self,
        order_id: str,
        order_flag: str,
        leg_name: str,
        quantity: int,
        price: Decimal,
        trigger_price: Decimal,
    ) -> Order:
        return self.modify_gtt(order_id, order_flag, leg_name, quantity, price, trigger_price)

    def cancel_forever_order(self, order_id: str) -> bool:
        return self.cancel_gtt(order_id)

    def get_forever_orders(self) -> list[Order]:
        # TODO: Upstox API has no list-all endpoint for GTT orders.
        # The client only supports fetching a single GTT by ID (get_gtt_orders),
        # so there is no way to enumerate all active forever orders.
        return []

    def place_gtt_multi(
        self,
        request: Order,
        order_flag: str,
        **kwargs: Any,
    ) -> Order:
        return self.place_gtt_single(request, order_flag, **kwargs)

    def modify_gtt(
        self,
        order_id: str,
        order_flag: str,
        leg_name: str,
        quantity: int,
        price: Decimal,
        trigger_price: Decimal,
    ) -> Order:
        payload = {
            "gtt_order_id": order_id,
            "order_flag": order_flag,
            "leg_name": leg_name,
            "quantity": int(quantity),
            "price": to_wire_float(price),
            "trigger_price": to_wire_float(trigger_price),
        }
        self._client.modify_gtt(order_id, payload)
        return Order(order_id=order_id)

    def cancel_gtt(self, order_id: str) -> bool:
        try:
            self._client.cancel_gtt(order_id)
            return True
        except Exception:
            return False

    def get_gtt_orders(self) -> list[Order]:
        # TODO: Upstox API has no list-all endpoint for GTT orders.
        # The client only supports fetching a single GTT by ID (get_gtt_orders),
        # so there is no way to enumerate all active GTT orders.
        return []

    def place_alert(self, request: ConditionalAlertRequest) -> str:
        body = self._client.place_gtt_single(
            {
                "type": "SINGLE",
                "instrument_token": request.symbol,
                "quantity": request.quantity,
                "rules": [
                    {
                        "strategy": "ENTRY",
                        "trigger_type": request.operator or "ABOVE",
                        "trigger_price": to_wire_float(
                            request.comparing_value or request.price or 0
                        ),
                    }
                ],
            }
        )
        if isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, dict):
                return str(data.get("gtt_order_id") or data.get("order_id") or "")
        return ""

    def get_alert(self, alert_id: str) -> ConditionalAlert:
        body = self._client.get_gtt_order_details(alert_id)
        if isinstance(body, dict):
            return ConditionalAlert(alert_id=alert_id, status=str(body.get("status") or ""))
        return ConditionalAlert(alert_id=alert_id)

    def list_alerts(self) -> list[ConditionalAlert]:
        # TODO: Upstox API has no list-all endpoint for GTT orders.
        # Alerts are implemented as GTT orders under the hood, so they share
        # the same limitation — no enumeration endpoint exists.
        return []

    def delete_alert(self, alert_id: str) -> bool:
        return self.cancel_gtt(alert_id)

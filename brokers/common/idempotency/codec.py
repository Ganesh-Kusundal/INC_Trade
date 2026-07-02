"""Serialize domain order types for durable idempotency storage."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from domain import Order, OrderResponse, OrderStatus, OrderType, ProductType, Side, Validity


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _parse_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def order_to_payload(order: Order) -> dict[str, Any]:
    return {
        "__type__": "Order",
        "order_id": order.order_id,
        "symbol": order.symbol,
        "exchange": order.exchange,
        "side": _enum_value(order.side),
        "order_type": _enum_value(order.order_type),
        "quantity": order.quantity,
        "filled_quantity": order.filled_quantity,
        "price": str(order.price),
        "trigger_price": str(order.trigger_price),
        "status": _enum_value(order.status),
        "timestamp": order.timestamp.isoformat() if order.timestamp else None,
        "product_type": _enum_value(order.product_type),
        "validity": _enum_value(order.validity),
        "avg_price": str(order.avg_price),
        "reject_reason": order.reject_reason,
        "correlation_id": order.correlation_id,
        "instrument_id": order.instrument_id,
    }


def order_from_payload(payload: dict[str, Any]) -> Order:
    timestamp_raw = payload.get("timestamp")
    timestamp = datetime.fromisoformat(timestamp_raw) if timestamp_raw else None
    return Order(
        order_id=str(payload["order_id"]),
        symbol=str(payload["symbol"]),
        exchange=str(payload["exchange"]),
        side=Side(str(payload["side"])),
        order_type=OrderType(str(payload["order_type"])),
        quantity=int(payload["quantity"]),
        filled_quantity=int(payload.get("filled_quantity", 0)),
        price=_parse_decimal(payload.get("price", "0")),
        trigger_price=_parse_decimal(payload.get("trigger_price", "0")),
        status=OrderStatus(str(payload["status"])),
        timestamp=timestamp,
        product_type=ProductType(str(payload["product_type"])),
        validity=Validity(str(payload["validity"])),
        avg_price=_parse_decimal(payload.get("avg_price", "0")),
        reject_reason=str(payload.get("reject_reason", "")),
        correlation_id=payload.get("correlation_id"),
        instrument_id=payload.get("instrument_id"),
    )


def order_response_to_payload(response: OrderResponse) -> dict[str, Any]:
    return {
        "__type__": "OrderResponse",
        "success": response.success,
        "order_id": response.order_id,
        "message": response.message,
        "status": _enum_value(response.status),
        "broker_order_id": response.broker_order_id,
        "error_code": response.error_code,
        "http_status": response.http_status,
        "raw_payload": response.raw_payload,
        "latency_ms": response.latency_ms,
    }


def order_response_from_payload(payload: dict[str, Any]) -> OrderResponse:
    return OrderResponse(
        success=bool(payload["success"]),
        order_id=str(payload.get("order_id", "")),
        message=str(payload.get("message", "")),
        status=OrderStatus(str(payload.get("status", OrderStatus.OPEN.value))),
        broker_order_id=str(payload.get("broker_order_id", "")),
        error_code=str(payload.get("error_code", "")),
        http_status=payload.get("http_status"),
        raw_payload=payload.get("raw_payload"),
        latency_ms=float(payload.get("latency_ms", 0.0)),
    )


def decode_idempotency_payload(payload: dict[str, Any]) -> Order | OrderResponse:
    kind = payload.get("__type__")
    if kind == "Order":
        return order_from_payload(payload)
    if kind == "OrderResponse":
        return order_response_from_payload(payload)
    raise ValueError(f"Unsupported idempotency payload type: {kind!r}")


def encode_idempotency_value(value: Order | OrderResponse) -> dict[str, Any]:
    if isinstance(value, Order):
        return order_to_payload(value)
    if isinstance(value, OrderResponse):
        return order_response_to_payload(value)
    raise TypeError(f"Unsupported idempotency value type: {type(value).__name__}")

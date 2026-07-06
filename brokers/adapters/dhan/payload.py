"""Dhan wire-format payload construction — shared by place and slice orders.

Both ``PlaceOrderUseCase.execute()`` (regular /v2/orders) and
``DhanOrders.place_slice_order()`` (/v2/sliceorder) build the same wire
dict. This module owns that single source of truth so the two call sites
cannot drift (A-3 remediation).

The builder is intentionally endpoint-agnostic — it does not pick between
``orders`` and ``sliceorder``. That decision is made by the caller after
the payload is built and validated.
"""

from __future__ import annotations

import uuid

from brokers.domain.entities import OrderRequest
from brokers.utils.price import wire_price_or_zero

from brokers.adapters.dhan.identity import DhanInstrumentRef


def build_dhan_order_payload(
    *,
    client_id: str,
    request: OrderRequest,
    ref: DhanInstrumentRef,
    side_map: dict[str, int],
    order_type_map: dict[str, int],
    product_type_map: dict[str, str],
    validity_map: dict[str, str],
) -> dict[str, object]:
    """Build a wire-format Dhan order payload.

    Used by both ``PlaceOrderUseCase.execute()`` and
    ``DhanOrders.place_slice_order()``. Does NOT include endpoint
    selection — the caller picks the endpoint (regular vs. slice).

    The dict shape is part of the Dhan wire contract: keys and value
    types must remain identical to what the broker expects.
    """
    cid = request.correlation_id or str(uuid.uuid4())
    return {
        "dhanClientId": client_id,
        "transactionType": side_map.get(request.side.value, 1),
        "exchangeSegment": ref.exchange_segment,
        "securityId": ref.security_id_str(),
        "quantity": request.quantity,
        "orderType": order_type_map.get(request.order_type.value, 1),
        "productType": product_type_map.get(request.product_type.value, "INTRADAY"),
        "validity": validity_map.get(request.validity.value, "DAY"),
        "price": wire_price_or_zero(request.price),
        "triggerPrice": wire_price_or_zero(request.trigger_price),
        "correlationId": cid,
    }


__all__ = ["build_dhan_order_payload"]

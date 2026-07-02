"""NativeSliceOrderProvider extension interface.

Capability gate: ``BrokerCapabilities.supports_native_slice_order``
Supported by: Dhan (server-side /sliceorder endpoint)
Not supported by: Upstox (client-side slicing with 100ms spacing — a different
                          failure mode; partial fills on process crash leave exposure)

The distinction matters for risk: Dhan's server-side slice is atomic from the
broker's perspective; Upstox client-side slicing is not.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from domain.entities import OrderResponse
from domain.enums import OrderType, ProductType, Side, Validity


@dataclass(frozen=True)
class SliceOrderSpec:
    """Input for a server-side slice order."""

    symbol: str
    exchange: str
    side: Side
    quantity: int
    order_type: OrderType = OrderType.MARKET
    product_type: ProductType = ProductType.INTRADAY
    validity: Validity = Validity.DAY
    correlation_id: str | None = None


class NativeSliceOrderProvider(Protocol):
    """Extension interface for server-side order slicing."""

    async def place_slice_order(
        self,
        spec: SliceOrderSpec,
        *,
        quota: object,
    ) -> Sequence[OrderResponse]:
        """Place a server-side slice order. Returns responses for each child order."""
        ...

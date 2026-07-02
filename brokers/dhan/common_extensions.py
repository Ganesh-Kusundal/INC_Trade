"""Dhan extension providers for ExtensionRegistry."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from brokers.common.broker_port import QuotaToken
from brokers.common.extensions import ExtensionBundle, register_extension_factory
from brokers.common.extensions.forever_order import (
    ForeverOrderProvider,
    ForeverOrderRequest,
    ForeverOrderResult,
)
from brokers.common.extensions.native_slice_order import (
    NativeSliceOrderProvider,
    SliceOrderSpec,
)
from brokers.common.extensions.super_order import (
    SuperOrderProvider,
    SuperOrderRequest,
    SuperOrderResult,
)
from brokers.common.gateway import MarketDataGateway


class DhanSuperOrderExtension(SuperOrderProvider):
    def __init__(self, gateway: MarketDataGateway) -> None:
        self._extended = gateway.extended

    async def place_super_order(
        self, request: SuperOrderRequest, *, quota: QuotaToken
    ) -> SuperOrderResult:
        result = self._extended.place_super_order(
            symbol=request.symbol,
            exchange=request.exchange,
            side=request.side.value,
            quantity=request.quantity,
            price=request.entry_price,
            target=request.target_price,
            stop_loss=request.stop_loss_price,
            trailing_jump=request.trailing_jump,
            order_type=request.order_type.value,
            product_type=request.product_type.value,
        )
        order_id = str(getattr(result, "order_id", "") or result.get("order_id", ""))
        return SuperOrderResult(
            success=bool(order_id),
            entry_order_id=order_id,
            message="placed" if order_id else "failed",
        )

    async def cancel_super_order(
        self, entry_order_id: str, *, quota: QuotaToken
    ) -> SuperOrderResult:
        self._extended.cancel_super_order_leg(entry_order_id, "ENTRY")
        return SuperOrderResult(success=True, entry_order_id=entry_order_id)

    async def modify_super_order(
        self,
        entry_order_id: str,
        *,
        target_price: Decimal | None = None,
        stop_loss_price: Decimal | None = None,
        trailing_jump: Decimal | None = None,
        quota: QuotaToken,
    ) -> SuperOrderResult:
        kwargs: dict[str, Any] = {}
        if target_price is not None:
            kwargs["target"] = target_price
        if stop_loss_price is not None:
            kwargs["stop_loss"] = stop_loss_price
        if trailing_jump is not None:
            kwargs["trailing_jump"] = trailing_jump
        self._extended.modify_super_order(entry_order_id, **kwargs)
        return SuperOrderResult(success=True, entry_order_id=entry_order_id)


class DhanForeverOrderExtension(ForeverOrderProvider):
    def __init__(self, gateway: MarketDataGateway) -> None:
        self._extended = gateway.extended

    async def place_forever_order(
        self, request: ForeverOrderRequest, *, quota: object
    ) -> ForeverOrderResult:
        result = self._extended.place_forever_order(
            symbol=request.symbol,
            exchange=request.exchange,
            side=request.side.value,
            quantity=request.quantity,
            price=request.price1,
            trigger=request.trigger1,
            order_flag=request.order_flag,
        )
        order_id = str(getattr(result, "order_id", "") or "")
        return ForeverOrderResult(success=bool(order_id), order_id=order_id)

    async def cancel_forever_order(self, order_id: str, *, quota: object) -> ForeverOrderResult:
        self._extended.cancel_forever_order(order_id)
        return ForeverOrderResult(success=True, order_id=order_id)

    async def modify_forever_order(
        self,
        order_id: str,
        *,
        price1: Decimal | None = None,
        trigger1: Decimal | None = None,
        price2: Decimal | None = None,
        trigger2: Decimal | None = None,
        quota: object,
    ) -> ForeverOrderResult:
        kwargs: dict[str, Any] = {}
        if price1 is not None:
            kwargs["price"] = price1
        if trigger1 is not None:
            kwargs["trigger"] = trigger1
        self._extended.modify_forever_order(order_id, **kwargs)
        return ForeverOrderResult(success=True, order_id=order_id)


class DhanNativeSliceExtension(NativeSliceOrderProvider):
    def __init__(self, gateway: MarketDataGateway) -> None:
        self._orders = gateway.extended.orders

    async def place_slice_order(self, spec: SliceOrderSpec, *, quota: object) -> Sequence[Any]:
        return [
            self._orders.place_slice_order(
                symbol=spec.symbol,
                exchange=spec.exchange,
                side=spec.side.value,
                quantity=spec.quantity,
                order_type=spec.order_type.value,
                product_type=spec.product_type.value,
            )
        ]


def register_dhan_extensions(gateway: MarketDataGateway) -> ExtensionBundle:
    bundle = ExtensionBundle("dhan")
    bundle.register(SuperOrderProvider, DhanSuperOrderExtension(gateway))
    bundle.register(ForeverOrderProvider, DhanForeverOrderExtension(gateway))
    bundle.register(NativeSliceOrderProvider, DhanNativeSliceExtension(gateway))
    return bundle


register_extension_factory("dhan", register_dhan_extensions)

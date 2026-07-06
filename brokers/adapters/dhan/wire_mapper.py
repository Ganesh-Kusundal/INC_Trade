"""Dhan adapter wire mapper — translates domain enums to Dhan wire codes."""

from __future__ import annotations

from brokers.domain.enums import OrderType, ProductType, Side, Validity


class DhanWireMapper:
    """Translates domain enums to Dhan API wire codes.

    Dhan uses integer codes for Side and OrderType, and string codes
    for ProductType and Validity.
    """

    _SIDE_MAP: dict[Side, int] = {
        Side.BUY: 1,
        Side.SELL: 2,
    }

    _SIDE_MAP_REVERSE: dict[int, Side] = {v: k for k, v in _SIDE_MAP.items()}

    _ORDER_TYPE_MAP: dict[OrderType, int] = {
        OrderType.MARKET: 1,
        OrderType.LIMIT: 2,
        OrderType.STOP_LOSS: 3,
        OrderType.STOP_LOSS_MARKET: 4,
    }

    _ORDER_TYPE_MAP_REVERSE: dict[int, OrderType] = {v: k for k, v in _ORDER_TYPE_MAP.items()}

    _PRODUCT_TYPE_MAP: dict[ProductType, str] = {
        ProductType.INTRADAY: "INTRADAY",
        ProductType.DELIVERY: "MARGIN",
        ProductType.MARGIN: "MARGIN",
    }

    _PRODUCT_TYPE_MAP_REVERSE: dict[str, ProductType] = {
        "INTRADAY": ProductType.INTRADAY,
        "MARGIN": ProductType.MARGIN,
    }

    _VALIDITY_MAP: dict[Validity, str] = {
        Validity.DAY: "DAY",
        Validity.IOC: "IOC",
        Validity.GTT: "GTT",
    }

    def map_side(self, side: Side) -> int:
        return self._SIDE_MAP[side]

    def map_order_type(self, order_type: OrderType) -> int:
        return self._ORDER_TYPE_MAP[order_type]

    def map_product_type(self, product_type: ProductType) -> str:
        return self._PRODUCT_TYPE_MAP[product_type]

    def map_validity(self, validity: Validity) -> str:
        return self._VALIDITY_MAP[validity]

    def unmap_order_type(self, wire_code: int) -> OrderType:
        return self._ORDER_TYPE_MAP_REVERSE[wire_code]

    def unmap_product_type(self, wire_code: str) -> ProductType:
        return self._PRODUCT_TYPE_MAP_REVERSE[wire_code]

    def unmap_side(self, wire_code: int) -> Side:
        return self._SIDE_MAP_REVERSE[wire_code]

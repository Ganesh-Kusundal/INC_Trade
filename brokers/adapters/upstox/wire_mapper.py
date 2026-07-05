"""Upstox adapter wire mapper — translates domain enums to Upstox wire codes."""

from __future__ import annotations

from inc_trade.domain.enums import OrderType, ProductType, Side, Validity


class UpstoxWireMapper:
    """Translates domain enums to Upstox API wire codes.

    Upstox uses string codes for all enum types, with some abbreviations
    (e.g., "SL" for STOP_LOSS, "I" for INTRADAY).
    """

    _SIDE_MAP: dict[Side, str] = {
        Side.BUY: "BUY",
        Side.SELL: "SELL",
    }

    _SIDE_MAP_REVERSE: dict[str, Side] = {v: k for k, v in _SIDE_MAP.items()}

    _ORDER_TYPE_MAP: dict[OrderType, str] = {
        OrderType.MARKET: "MARKET",
        OrderType.LIMIT: "LIMIT",
        OrderType.STOP_LOSS: "SL",
        OrderType.STOP_LOSS_MARKET: "SL-M",
    }

    _ORDER_TYPE_MAP_REVERSE: dict[str, OrderType] = {
        "MARKET": OrderType.MARKET,
        "MKT": OrderType.MARKET,
        "LIMIT": OrderType.LIMIT,
        "LMT": OrderType.LIMIT,
        "SL": OrderType.STOP_LOSS,
        "STOP_LOSS": OrderType.STOP_LOSS,
        "SL-M": OrderType.STOP_LOSS_MARKET,
        "SLM": OrderType.STOP_LOSS_MARKET,
    }

    _PRODUCT_TYPE_MAP: dict[ProductType, str] = {
        ProductType.INTRADAY: "I",
        ProductType.DELIVERY: "D",
        ProductType.MARGIN: "D",
    }

    _PRODUCT_TYPE_MAP_REVERSE: dict[str, ProductType] = {
        "I": ProductType.INTRADAY,
        "D": ProductType.DELIVERY,
        "MTF": ProductType.DELIVERY,
    }

    _VALIDITY_MAP: dict[Validity, str] = {
        Validity.DAY: "DAY",
        Validity.IOC: "IOC",
    }

    def map_side(self, side: Side) -> str:
        return self._SIDE_MAP[side]

    def map_order_type(self, order_type: OrderType) -> str:
        return self._ORDER_TYPE_MAP[order_type]

    def map_product_type(self, product_type: ProductType) -> str:
        return self._PRODUCT_TYPE_MAP[product_type]

    def map_validity(self, validity: Validity) -> str:
        return self._VALIDITY_MAP[validity]

    def unmap_order_type(self, wire_code: str) -> OrderType:
        return self._ORDER_TYPE_MAP_REVERSE[wire_code]

    def unmap_product_type(self, wire_code: str) -> ProductType:
        return self._PRODUCT_TYPE_MAP_REVERSE[wire_code]

    def unmap_side(self, wire_code: str) -> Side:
        return self._SIDE_MAP_REVERSE[wire_code]

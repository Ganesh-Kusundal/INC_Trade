"""Default field mapping implementation for Order.from_broker_dict.

Provides a fallback mapping that handles both camelCase (Dhan-style) and
snake_case field names. Broker adapters can provide their own implementations
of the FieldMapping protocol for broker-specific field names.
"""

from domain.entities import FieldMapping


class DefaultFieldMapping(FieldMapping):
    """Default field name mapping supporting both camelCase and snake_case.

    This is used as the fallback when no broker-specific mapping is provided.
    It handles common field name variations:
    - orderId / order_id
    - tradingSymbol / symbol
    - exchangeSegment / exchange
    - transactionType / side
    - orderType / order_type
    - orderStatus / status
    - filledQty / filled_quantity
    - averagePrice / avg_price / average_price
    - rejectReason / reject_reason
    """

    def map_order_id(self, data: dict) -> str:
        return str(data.get("orderId", data.get("order_id", "")))

    def map_symbol(self, data: dict) -> str:
        return str(data.get("tradingSymbol", data.get("symbol", "")))

    def map_exchange(self, data: dict) -> str:
        return str(data.get("exchangeSegment", data.get("exchange", "NSE")))

    def map_side(self, data: dict) -> str:
        return str(data.get("transactionType", data.get("side", "BUY"))).upper()

    def map_order_type(self, data: dict) -> str:
        raw = str(data.get("orderType", data.get("order_type", "MARKET"))).upper()
        aliases = {
            "STOPLOSS_LIMIT": "STOP_LOSS",
            "STOPLOSS_MARKET": "STOP_LOSS_MARKET",
            "STOPLOSS-MARKET": "STOP_LOSS_MARKET",
            "SL": "STOP_LOSS",
            "SLM": "STOP_LOSS_MARKET",
        }
        return aliases.get(raw, raw)

    def map_status(self, data: dict) -> str:
        return str(data.get("orderStatus", data.get("status", "OPEN"))).upper()

    def map_quantity(self, data: dict) -> int:
        return int(data.get("quantity", 0))

    def map_filled_quantity(self, data: dict) -> int:
        return int(data.get("filledQty", data.get("filled_quantity", 0)))

    def map_price(self, data: dict) -> str | None:
        v = data.get("price")
        return None if v in (None, "") else str(v)

    def map_avg_price(self, data: dict) -> str | None:
        v = data.get("averagePrice", data.get("avg_price", data.get("average_price")))
        return None if v in (None, "") else str(v)

    def map_reject_reason(self, data: dict) -> str:
        return str(data.get("rejectReason", data.get("reject_reason", "")))

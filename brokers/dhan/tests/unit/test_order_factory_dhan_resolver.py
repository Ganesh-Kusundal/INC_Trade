"""Dhan-specific resolver test for Order.from_broker_dict."""

from __future__ import annotations

from domain.entities import Order


class TestDhanExchangeResolver:
    """The optional ``exchange_resolver`` lets adapters map segments to Dhan enums."""

    def test_exchange_resolver_can_map_to_dhan_exchange_enum(self):
        from brokers.dhan.domain import Exchange as DhanExchange

        def dhan_resolver(seg: str) -> DhanExchange:
            from brokers.dhan.segments import SEGMENT_TO_EXCHANGE

            return DhanExchange(SEGMENT_TO_EXCHANGE.get(str(seg), "NSE"))

        raw = {
            "orderId": "ORD-D",
            "tradingSymbol": "RELIANCE",
            "exchangeSegment": "NSE_EQ",
            "transactionType": "BUY",
            "orderType": "MARKET",
            "quantity": 1,
            "orderStatus": "OPEN",
        }
        order = Order.from_broker_dict(raw, exchange_resolver=dhan_resolver)
        assert order.exchange == DhanExchange.NSE

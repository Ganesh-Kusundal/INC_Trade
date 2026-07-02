"""Tests for domain.events.types — EventType enum, payload contracts, typed events."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from domain.entities.order import Order
from domain.entities.trade import Trade
from domain.events.types import (
    EVENT_PAYLOADS,
    EventPayload,
    EventType,
    OrderUpdatedEvent,
    TradeAppliedEvent,
    TradeFilledEvent,
    canonical_event_types,
    make_payload,
)
from domain.types import OrderStatus, OrderType, Side


class TestEventType:
    def test_is_str_enum(self):
        assert isinstance(EventType.TICK, str)

    def test_tick_equals_string(self):
        assert EventType.TICK == "TICK"

    def test_trade_equals_string(self):
        assert EventType.TRADE == "TRADE"

    def test_order_updated_equals_string(self):
        assert EventType.ORDER_UPDATED == "ORDER_UPDATED"

    def test_all_market_events_exist(self):
        assert EventType.TICK
        assert EventType.DEPTH
        assert EventType.INDEX_QUOTE
        assert EventType.OPTION_CHAIN

    def test_all_oms_events_exist(self):
        assert EventType.ORDER_PLACED
        assert EventType.ORDER_UPDATED
        assert EventType.ORDER_CANCELLED
        assert EventType.ORDER_REJECTED
        assert EventType.TRADE
        assert EventType.TRADE_APPLIED

    def test_risk_events_exist(self):
        assert EventType.RISK_BREACH
        assert EventType.KILL_SWITCH_FLIPPED
        assert EventType.RISK_VIOLATED
        assert EventType.DRAWDOWN_LIMIT_HIT


class TestCanonicalEventTypes:
    def test_returns_frozenset(self):
        result = canonical_event_types()
        assert isinstance(result, frozenset)

    def test_contains_all_event_types(self):
        result = canonical_event_types()
        for et in EventType:
            assert et.value in result

    def test_count_matches_enum(self):
        assert len(canonical_event_types()) == len(EventType)


class TestEventPayloads:
    def test_every_event_type_has_payload_contract(self):
        for et in EventType:
            assert et in EVENT_PAYLOADS, f"{et} missing from EVENT_PAYLOADS"

    def test_tick_payload_has_optional_keys(self):
        contract = EVENT_PAYLOADS[EventType.TICK]
        assert "ltp" in contract.optional_keys

    def test_trade_payload_requires_trade_key(self):
        contract = EVENT_PAYLOADS[EventType.TRADE]
        assert "trade" in contract.required_keys


class TestMakePayload:
    def test_no_validate_is_passthrough(self):
        payload = {"anything": "goes"}
        result = make_payload(EventType.TICK, payload)
        assert result is payload

    def test_validate_success(self):
        payload = {"order": "fake_order"}
        result = make_payload(EventType.ORDER_PLACED, payload, validate=True)
        assert result is payload

    def test_validate_missing_required_key_raises(self):
        with pytest.raises(KeyError, match="missing required keys"):
            make_payload(EventType.ORDER_PLACED, {}, validate=True)

    def test_validate_unknown_event_type_passes(self):
        payload = {"data": 123}
        result = make_payload("NONEXISTENT_EVENT", payload, validate=True)
        assert result is payload

    @pytest.mark.parametrize("event_type", list(EventType))
    def test_validate_passes_with_all_required_keys(self, event_type):
        contract = EVENT_PAYLOADS.get(event_type)
        if contract is None or not contract.required_keys:
            return
        payload = {k: "value" for k in contract.required_keys}
        result = make_payload(event_type, payload, validate=True)
        assert result is payload

    @pytest.mark.parametrize(
        "event_type",
        [et for et in EventType if EVENT_PAYLOADS.get(et, EventPayload()).required_keys],
    )
    def test_validate_rejects_empty_payload_for_events_with_required_keys(self, event_type):
        with pytest.raises(KeyError, match="missing required keys"):
            make_payload(event_type, {}, validate=True)


class TestOrderUpdatedEvent:
    def _make_order(self):
        return Order(
            order_id="O-1",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            order_type=OrderType.LIMIT,
            quantity=10,
        )

    def test_from_domain_event(self):
        order = self._make_order()
        event = MagicMock()
        event.payload = {"order": order}
        event.event_type = "ORDER_UPDATED"
        event.event_id = "evt-1"
        event.correlation_id = "corr-1"

        typed = OrderUpdatedEvent.from_domain_event(event)
        assert typed.order is order
        assert typed.event_type == "ORDER_UPDATED"
        assert typed.event_id == "evt-1"
        assert typed.correlation_id == "corr-1"

    def test_raises_on_missing_order(self):
        event = MagicMock()
        event.payload = {}
        with pytest.raises(ValueError, match="must contain Order"):
            OrderUpdatedEvent.from_domain_event(event)

    def test_raises_on_wrong_type(self):
        event = MagicMock()
        event.payload = {"order": "not_an_order"}
        with pytest.raises(ValueError, match="must contain Order"):
            OrderUpdatedEvent.from_domain_event(event)


class TestTradeFilledEvent:
    def _make_trade(self):
        return Trade(
            trade_id="T-1",
            order_id="O-1",
            symbol="RELIANCE",
            exchange="NSE",
            side=Side.BUY,
            quantity=10,
            price=Decimal("2500"),
        )

    def test_from_domain_event(self):
        trade = self._make_trade()
        event = MagicMock()
        event.payload = {"trade": trade}
        event.event_type = "TRADE"
        event.event_id = "evt-2"
        event.correlation_id = None

        typed = TradeFilledEvent.from_domain_event(event)
        assert typed.trade is trade
        assert typed.event_type == "TRADE"

    def test_raises_on_missing_trade(self):
        event = MagicMock()
        event.payload = {}
        with pytest.raises(ValueError, match="must contain Trade"):
            TradeFilledEvent.from_domain_event(event)


class TestTradeAppliedEvent:
    def _make_trade(self):
        return Trade(
            trade_id="T-2",
            order_id="O-2",
            symbol="TCS",
            exchange="BSE",
            side=Side.SELL,
            quantity=5,
        )

    def test_from_domain_event(self):
        trade = self._make_trade()
        event = MagicMock()
        event.payload = {"trade": trade}
        event.event_type = "TRADE_APPLIED"
        event.event_id = "evt-3"
        event.correlation_id = "corr-3"

        typed = TradeAppliedEvent.from_domain_event(event)
        assert typed.trade is trade
        assert typed.correlation_id == "corr-3"

    def test_raises_on_wrong_type(self):
        event = MagicMock()
        event.payload = {"trade": 42}
        with pytest.raises(ValueError, match="must contain Trade"):
            TradeAppliedEvent.from_domain_event(event)

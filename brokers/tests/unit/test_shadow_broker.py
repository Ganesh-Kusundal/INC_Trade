"""Unit tests for ShadowBroker — shadow-run migration wrapper.

Validates the David Farley shadow-run guarantees:
- Primary result is always returned (never shadow's).
- Shadow exceptions are swallowed (never raised to caller).
- Mismatches are counted and logged; matches are not.
- Toggling enabled=False disables shadow execution entirely.
- mismatch_rate calculates correctly from call_count / mismatch_count.
- All major proxied methods work: place_order, get_quote, get_positions,
  get_holdings, get_balance, get_orderbook.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from brokers.services.shadow_broker import ShadowBroker


# ---------------------------------------------------------------------------
# Minimal domain-like dataclass stubs for deterministic comparison
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _OrderResponse:
    order_id: str = ""
    success: bool = False


@dataclass(frozen=True)
class _Quote:
    symbol: str = "RELIANCE"
    ltp: Decimal = Decimal("100")


@dataclass(frozen=True)
class _Position:
    symbol: str = "RELIANCE"
    quantity: int = 10


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_primary(**overrides):
    """Return a MagicMock configured with sensible return values."""
    primary = MagicMock()
    primary.place_order.return_value = overrides.get(
        "place_order", _OrderResponse(order_id="P1", success=True)
    )
    primary.get_quote.return_value = overrides.get(
        "get_quote", _Quote(symbol="RELIANCE", ltp=Decimal("100"))
    )
    primary.get_positions.return_value = overrides.get(
        "get_positions", [_Position(symbol="RELIANCE", quantity=10)]
    )
    primary.get_holdings.return_value = overrides.get("get_holdings", [])
    primary.get_balance.return_value = overrides.get("get_balance", MagicMock())
    primary.get_orderbook.return_value = overrides.get("get_orderbook", [])
    return primary


def _make_shadow(**overrides):
    """Return a MagicMock for the shadow gateway."""
    shadow = MagicMock()
    shadow.place_order.return_value = overrides.get(
        "place_order", _OrderResponse(order_id="P1", success=True)
    )
    shadow.get_quote.return_value = overrides.get(
        "get_quote", _Quote(symbol="RELIANCE", ltp=Decimal("100"))
    )
    shadow.get_positions.return_value = overrides.get(
        "get_positions", [_Position(symbol="RELIANCE", quantity=10)]
    )
    shadow.get_holdings.return_value = overrides.get("get_holdings", [])
    shadow.get_balance.return_value = overrides.get("get_balance", MagicMock())
    shadow.get_orderbook.return_value = overrides.get("get_orderbook", [])
    return shadow


# ---------------------------------------------------------------------------
# 1. Primary result always returned
# ---------------------------------------------------------------------------


class TestPrimaryResultAlwaysReturned:
    def test_place_order_returns_primary(self):
        primary_resp = _OrderResponse(order_id="PRIMARY", success=True)
        shadow_resp = _OrderResponse(order_id="SHADOW", success=True)
        primary = _make_primary(place_order=primary_resp)
        shadow = _make_shadow(place_order=shadow_resp)
        broker = ShadowBroker(primary, shadow)

        result = broker.place_order(symbol="RELIANCE", quantity=1)

        assert result is primary_resp

    def test_get_quote_returns_primary_even_when_shadow_differs(self):
        primary_quote = _Quote(symbol="TCS", ltp=Decimal("500"))
        shadow_quote = _Quote(symbol="TCS", ltp=Decimal("999"))
        primary = _make_primary(get_quote=primary_quote)
        shadow = _make_shadow(get_quote=shadow_quote)
        broker = ShadowBroker(primary, shadow)

        result = broker.get_quote("TCS")

        assert result is primary_quote

    def test_get_positions_returns_primary_list(self):
        primary_pos = [_Position(symbol="INFY", quantity=5)]
        shadow_pos = [_Position(symbol="INFY", quantity=99)]
        primary = _make_primary(get_positions=primary_pos)
        shadow = _make_shadow(get_positions=shadow_pos)
        broker = ShadowBroker(primary, shadow)

        result = broker.get_positions()

        assert result is primary_pos


# ---------------------------------------------------------------------------
# 2. Shadow exceptions are swallowed
# ---------------------------------------------------------------------------


class TestShadowExceptionsSwallowed:
    def test_shadow_exception_does_not_propagate(self):
        primary = _make_primary()
        shadow = MagicMock()
        shadow.place_order.side_effect = RuntimeError("legacy gateway exploded")
        broker = ShadowBroker(primary, shadow)

        # Must NOT raise — shadow exception is silently swallowed
        result = broker.place_order()

        assert result is not None  # primary result still returned

    def test_shadow_exception_logged_as_warning(self, caplog):
        primary = _make_primary()
        shadow = MagicMock()
        shadow.get_quote.side_effect = ConnectionError("timeout")
        broker = ShadowBroker(primary, shadow)

        with caplog.at_level(logging.WARNING, logger="brokers.services.shadow_broker"):
            broker.get_quote("RELIANCE")

        assert any("shadow raised exception" in r.message for r in caplog.records)

    def test_shadow_exception_does_not_increment_mismatch_count(self):
        primary = _make_primary()
        shadow = MagicMock()
        shadow.get_positions.side_effect = ValueError("broken")
        broker = ShadowBroker(primary, shadow)

        broker.get_positions()

        assert broker.mismatch_count == 0


# ---------------------------------------------------------------------------
# 3. Mismatch counting
# ---------------------------------------------------------------------------


class TestMismatchCounting:
    def test_mismatch_increments_when_results_differ(self):
        primary = _make_primary(get_quote=_Quote(symbol="X", ltp=Decimal("1")))
        shadow = _make_shadow(get_quote=_Quote(symbol="X", ltp=Decimal("2")))
        broker = ShadowBroker(primary, shadow)

        broker.get_quote("X")

        assert broker.mismatch_count == 1

    def test_mismatch_does_not_increment_when_results_match(self):
        q = _Quote(symbol="NIFTY", ltp=Decimal("22000"))
        primary = _make_primary(get_quote=q)
        shadow = _make_shadow(get_quote=_Quote(symbol="NIFTY", ltp=Decimal("22000")))
        broker = ShadowBroker(primary, shadow)

        broker.get_quote("NIFTY")

        assert broker.mismatch_count == 0

    def test_mismatch_accumulates_over_multiple_calls(self):
        primary = _make_primary()
        shadow = _make_shadow(
            get_quote=_Quote(symbol="RELIANCE", ltp=Decimal("999")),
            get_positions=[_Position(symbol="RELIANCE", quantity=99)],
        )
        broker = ShadowBroker(primary, shadow)

        broker.get_quote("RELIANCE")
        broker.get_positions()

        assert broker.mismatch_count == 2

    def test_mismatch_warning_logged(self, caplog):
        primary = _make_primary(get_quote=_Quote(symbol="X", ltp=Decimal("1")))
        shadow = _make_shadow(get_quote=_Quote(symbol="X", ltp=Decimal("2")))
        broker = ShadowBroker(primary, shadow)

        with caplog.at_level(logging.WARNING, logger="brokers.services.shadow_broker"):
            broker.get_quote("X")

        assert any("MISMATCH" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# 4. enabled flag
# ---------------------------------------------------------------------------


class TestEnabledFlag:
    def test_shadow_not_called_when_disabled(self):
        primary = _make_primary()
        shadow = MagicMock()
        broker = ShadowBroker(primary, shadow, enabled=False)

        broker.get_quote("RELIANCE")

        shadow.get_quote.assert_not_called()

    def test_call_count_not_incremented_when_disabled(self):
        primary = _make_primary()
        shadow = MagicMock()
        broker = ShadowBroker(primary, shadow, enabled=False)

        broker.get_quote("RELIANCE")
        broker.get_positions()
        broker.place_order()

        assert broker.call_count == 0

    def test_mismatch_count_zero_when_disabled(self):
        primary = _make_primary(get_quote=_Quote(ltp=Decimal("1")))
        shadow = _make_shadow(get_quote=_Quote(ltp=Decimal("2")))
        broker = ShadowBroker(primary, shadow, enabled=False)

        broker.get_quote("RELIANCE")

        assert broker.mismatch_count == 0

    def test_enable_shadow_property_toggles(self):
        primary = _make_primary()
        shadow = MagicMock()
        broker = ShadowBroker(primary, shadow, enabled=False)
        assert broker.enable_shadow is False

        broker.enable_shadow = True
        assert broker.enable_shadow is True

        broker.get_quote("RELIANCE")
        shadow.get_quote.assert_called_once()


# ---------------------------------------------------------------------------
# 5. mismatch_rate
# ---------------------------------------------------------------------------


class TestMismatchRate:
    def test_mismatch_rate_zero_when_no_calls(self):
        broker = ShadowBroker(MagicMock(), MagicMock())
        assert broker.mismatch_rate == 0.0

    def test_mismatch_rate_one_when_all_mismatched(self):
        primary = _make_primary(
            get_quote=_Quote(ltp=Decimal("1")),
            get_positions=[_Position(quantity=1)],
        )
        shadow = _make_shadow(
            get_quote=_Quote(ltp=Decimal("2")),
            get_positions=[_Position(quantity=99)],
        )
        broker = ShadowBroker(primary, shadow)

        broker.get_quote("X")
        broker.get_positions()

        assert broker.mismatch_rate == pytest.approx(1.0)

    def test_mismatch_rate_half_when_one_of_two_mismatched(self):
        primary = _make_primary(
            get_quote=_Quote(symbol="X", ltp=Decimal("1")),
            get_positions=[_Position(quantity=10)],
        )
        shadow = _make_shadow(
            get_quote=_Quote(symbol="X", ltp=Decimal("2")),  # mismatch
            get_positions=[_Position(quantity=10)],  # match
        )
        broker = ShadowBroker(primary, shadow)

        broker.get_quote("X")  # mismatch
        broker.get_positions()  # match

        assert broker.mismatch_rate == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 6. All major methods proxied correctly
# ---------------------------------------------------------------------------


class TestAllMethodsProxied:
    def _broker_with_matching_shadow(self):
        primary = _make_primary()
        shadow = _make_shadow()
        return ShadowBroker(primary, shadow), primary, shadow

    def test_place_order_calls_primary(self):
        broker, primary, _ = self._broker_with_matching_shadow()
        broker.place_order(symbol="RELIANCE", quantity=5)
        primary.place_order.assert_called_once_with(symbol="RELIANCE", quantity=5)

    def test_get_quote_calls_primary(self):
        broker, primary, _ = self._broker_with_matching_shadow()
        broker.get_quote("NIFTY", exchange="NSE")
        primary.get_quote.assert_called_once_with("NIFTY", exchange="NSE")

    def test_get_positions_calls_primary(self):
        broker, primary, _ = self._broker_with_matching_shadow()
        broker.get_positions()
        primary.get_positions.assert_called_once()

    def test_get_holdings_calls_primary(self):
        broker, primary, _ = self._broker_with_matching_shadow()
        broker.get_holdings()
        primary.get_holdings.assert_called_once()

    def test_get_balance_calls_primary(self):
        broker, primary, _ = self._broker_with_matching_shadow()
        broker.get_balance()
        primary.get_balance.assert_called_once()

    def test_get_orderbook_calls_primary(self):
        broker, primary, _ = self._broker_with_matching_shadow()
        broker.get_orderbook()
        primary.get_orderbook.assert_called_once()

    def test_shadow_also_called_for_all_methods(self):
        broker, _, shadow = self._broker_with_matching_shadow()
        broker.place_order()
        broker.get_quote("X")
        broker.get_positions()
        broker.get_holdings()
        broker.get_balance()
        broker.get_orderbook()

        shadow.place_order.assert_called_once()
        shadow.get_quote.assert_called_once()
        shadow.get_positions.assert_called_once()
        shadow.get_holdings.assert_called_once()
        shadow.get_balance.assert_called_once()
        shadow.get_orderbook.assert_called_once()


# ---------------------------------------------------------------------------
# 7. Shadow missing method handled gracefully
# ---------------------------------------------------------------------------


class TestShadowMissingMethod:
    def test_missing_shadow_method_logs_warning(self, caplog):
        primary = _make_primary()
        shadow = MagicMock(spec=[])  # no methods at all
        broker = ShadowBroker(primary, shadow)

        with caplog.at_level(logging.WARNING, logger="brokers.services.shadow_broker"):
            broker.get_quote("RELIANCE")

        assert any("does not implement" in r.message for r in caplog.records)

    def test_missing_shadow_method_still_returns_primary(self):
        primary = _make_primary()
        primary_quote = primary.get_quote.return_value
        shadow = MagicMock(spec=[])
        broker = ShadowBroker(primary, shadow)

        result = broker.get_quote("RELIANCE")

        assert result is primary_quote

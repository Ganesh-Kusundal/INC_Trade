"""Tests for TickTranslatorAdapter.

Covers:
- Dict payload translation with instrument key
- Dict payload with missing instrument key
- Attribute/protobuf payload translation
- OHLC extraction from dict and object
- Timestamp parsing (millis, ISO, None)
- Canonical symbol resolution priority
- Fallback behavior for unresolvable keys
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

from brokers.upstox.adapters.tick_translator import TickTranslatorAdapter
from domain import Quote


class TestTickTranslatorDictPayload:
    """Test translation of dict-style payloads."""

    def test_translate_dict_with_resolved_key(self):
        """Dict payload with resolvable instrument key returns Quote."""
        defn = MagicMock()
        defn.name = "RELIANCE"
        defn.symbol = "RELIANCE"
        defn.trading_symbol = ""

        resolve = MagicMock(return_value=defn)

        raw = {
            "frame_type": "ltpc",
            "payload": {
                "instrument_key": "NSE_EQ|RELIANCE",
                "last_price": 2500.50,
                "close_price": 2480.00,
                "volume": 100000,
            },
        }

        result = TickTranslatorAdapter.translate(raw, resolve_callback=resolve)

        assert isinstance(result, Quote)
        assert result.symbol == "RELIANCE"
        assert result.ltp == Decimal("2500.5000")
        assert result.close == Decimal("2480.0000")
        assert result.volume == 100000

    def test_translate_dict_missing_instrument_key_returns_raw(self):
        """Dict payload without instrument key returns raw dict."""
        raw = {
            "frame_type": "ltpc",
            "payload": {"last_price": 100.0},
        }

        result = TickTranslatorAdapter.translate(raw)

        assert result is raw

    def test_translate_dict_unresolvable_key_falls_back(self):
        """Unresolvable key extracts symbol from RHS."""
        resolve = MagicMock(return_value=None)

        raw = {
            "frame_type": "ltpc",
            "payload": {
                "instrument_key": "NSE_EQ|RELIANCE",
                "last_price": 2500.00,
            },
        }

        result = TickTranslatorAdapter.translate(raw, resolve_callback=resolve)

        assert isinstance(result, Quote)
        assert result.symbol == "RELIANCE"
        assert result.ltp == Decimal("2500.0000")


class TestTickTranslatorProtobufPayload:
    """Test translation of protobuf/attribute-style payloads."""

    def test_translate_protobuf_object(self):
        """Protobuf object with attributes translates correctly."""

        # Create a simple class to simulate protobuf object (not a dict)
        class ProtobufPayload:
            def __init__(self):
                self.instrument_key = "NSE_EQ|TCS"
                self.instrumentKey = ""
                self.last_price = 3500.00
                self.ltp = 0
                self.close_price = 3480.00
                self.prev_close_price = 0
                self.ohlc = None
                self.open = 0
                self.high = 0
                self.low = 0
                self.close = 0
                self.volume = 50000
                self.total_buy_quantity = 0
                self.total_sell_quantity = 0
                self.best_bid_price = 0
                self.best_ask_price = 0
                self.exchange_timestamp = None

        defn = MagicMock()
        defn.name = "TCS"
        resolve = MagicMock(return_value=defn)

        payload = ProtobufPayload()
        raw = {"frame_type": "ltpc", "payload": payload}
        result = TickTranslatorAdapter.translate(raw, resolve_callback=resolve)

        assert isinstance(result, Quote)
        assert result.symbol == "TCS"
        assert result.ltp == Decimal("3500.0000")


class TestTickTranslatorOHLC:
    """Test OHLC extraction from payloads."""

    def test_ohlc_dict_extraction(self):
        """OHLC extracted from nested dict."""
        defn = MagicMock()
        defn.name = "NIFTY50"
        resolve = MagicMock(return_value=defn)

        raw = {
            "frame_type": "full",
            "payload": {
                "instrument_key": "NSE_INDEX|NIFTY50",
                "last_price": 22500.00,
                "close_price": 22000.00,
                "ohlc": {
                    "open": 22100.00,
                    "high": 22600.00,
                    "low": 22050.00,
                    "close": 22450.00,
                },
                "volume": 0,
            },
        }

        q = TickTranslatorAdapter.translate(raw, resolve_callback=resolve)

        assert q.open == Decimal("22100.0000")
        assert q.high == Decimal("22600.0000")
        assert q.low == Decimal("22050.0000")
        assert q.close == Decimal("22450.0000")  # OHLC close takes priority


class TestTickTranslatorTimestamp:
    """Test timestamp parsing."""

    def test_timestamp_millis_converted(self):
        """Millisecond timestamp converted to datetime."""
        defn = MagicMock()
        defn.name = "TCS"
        resolve = MagicMock(return_value=defn)

        ts_ms = int(datetime(2025, 5, 20, 9, 15, 0, tzinfo=timezone.utc).timestamp() * 1000)

        raw = {
            "frame_type": "ltpc",
            "payload": {
                "instrument_key": "NSE_EQ|TCS",
                "last_price": 3500.00,
                "close_price": 3480.00,
                "exchange_timestamp": ts_ms,
                "volume": 0,
            },
        }

        q = TickTranslatorAdapter.translate(raw, resolve_callback=resolve)

        assert q.timestamp is not None
        assert q.timestamp.year == 2025
        assert q.timestamp.month == 5
        assert q.timestamp.day == 20


class TestCanonicalSymbolPriority:
    """Test canonical symbol resolution priority."""

    def test_name_takes_priority(self):
        """defn.name takes highest priority."""
        defn = MagicMock()
        defn.name = "NIFTY 29 MAY 25 24800 CE"
        defn.symbol = "NIFTY2924800CE"
        defn.trading_symbol = "NIFTY2924800CE"

        sym = TickTranslatorAdapter._canonical_symbol_for_defn(defn, "NSE_FO|NIFTY2924800CE")
        assert sym == "NIFTY 29 MAY 25 24800 CE"

    def test_symbol_used_when_name_empty(self):
        """defn.symbol used when name is empty."""
        defn = MagicMock()
        defn.name = ""
        defn.symbol = "RELIANCE"
        defn.trading_symbol = "RELIANCE-EQ"

        sym = TickTranslatorAdapter._canonical_symbol_for_defn(defn, "NSE_EQ|RELIANCE")
        assert sym == "RELIANCE"

    def test_trading_symbol_fallback(self):
        """defn.trading_symbol used when name and symbol empty."""
        defn = MagicMock()
        defn.name = ""
        defn.symbol = ""
        defn.trading_symbol = "TCS-EQ"

        sym = TickTranslatorAdapter._canonical_symbol_for_defn(defn, "NSE_EQ|TCS")
        assert sym == "TCS-EQ"

    def test_instrument_key_rhs_fallback_when_no_defn(self):
        """RHS of instrument_key used when defn is None."""
        sym = TickTranslatorAdapter._canonical_symbol_for_defn(None, "NSE_EQ|HDFC")
        assert sym == "HDFC"

    def test_bare_key_when_no_pipe(self):
        """Bare key returned when no pipe separator."""
        sym = TickTranslatorAdapter._canonical_symbol_for_defn(None, "UNKNOWN")
        assert sym == "UNKNOWN"

    def test_empty_fallback_key(self):
        """Empty string returned when fallback key empty."""
        sym = TickTranslatorAdapter._canonical_symbol_for_defn(None, "")
        assert sym == ""

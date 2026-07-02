"""Tick translator adapter — raw WebSocket tick to canonical Quote conversion.

Responsibility: Translate raw Upstox WebSocket tick payloads (dict or protobuf)
into canonical Quote domain objects.
Thread-safe: All methods are stateless and thread-safe.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from domain import Quote

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class TickTranslatorAdapter:
    """Adapter for translating raw WebSocket ticks to canonical Quote objects.

    Handles both dict payloads and protobuf-decoded objects from the Upstox
    V3 WebSocket multiplexer.

    Resolution flow:
    1. Extract instrument_key from payload
    2. Reverse-resolve key to instrument definition
    3. Derive canonical symbol
    4. Extract price fields (supports both dict and attribute access)
    5. Build and return Quote

    Thread Safety:
        All methods are stateless and thread-safe. The resolve_callback parameter
        allows dependency injection for instrument resolution.

    Example::

        translator = TickTranslatorAdapter()
        quote = translator.translate(raw_tick, resolve_callback=resolver.resolve)
    """

    @staticmethod
    def translate(
        raw: dict[str, Any] | Any,
        resolve_callback: Any | None = None,
    ) -> Quote | dict[str, Any]:
        """Translate a raw WebSocket tick frame into a canonical Quote.

        Args:
            raw: Raw tick dict or object with frame_type and payload
            resolve_callback: Callable(instrument_key) -> instrument_definition

        Returns:
            Quote object if translation succeeds, or raw dict if resolution fails

        Note:
            If the instrument_key cannot be resolved, the raw dict is returned
            unchanged so no data is silently dropped.
        """
        try:
            payload = raw.get("payload") if isinstance(raw, dict) else raw
            if payload is None:
                return raw

            # Extract instrument_key
            inst_key = TickTranslatorAdapter._extract_instrument_key(payload)
            if not inst_key:
                return raw

            # Resolve broker key → instrument definition
            defn = None
            if resolve_callback:
                defn = resolve_callback(instrument_key=inst_key)

            canonical_sym = TickTranslatorAdapter._canonical_symbol_for_defn(defn, inst_key)

            # Extract price fields
            ltp = TickTranslatorAdapter._extract_price(payload, ["last_price", "ltp"])
            close = TickTranslatorAdapter._extract_price(
                payload, ["close_price", "close", "prev_close_price"]
            )

            # OHLC extraction
            open_, high, low, ohlc_close = TickTranslatorAdapter._extract_ohlc(payload)
            if ohlc_close:
                close = ohlc_close

            # Volume
            volume = TickTranslatorAdapter._extract_int(payload, "volume") or (
                TickTranslatorAdapter._extract_int(payload, "total_buy_quantity")
                + TickTranslatorAdapter._extract_int(payload, "total_sell_quantity")
            )

            # Best bid/ask
            bid = TickTranslatorAdapter._extract_price(payload, ["best_bid_price"])
            ask = TickTranslatorAdapter._extract_price(payload, ["best_ask_price"])
            if bid is not None and bid == Decimal("0"):
                bid = None
            if ask is not None and ask == Decimal("0"):
                ask = None

            # Timestamp
            ts = TickTranslatorAdapter._extract_timestamp(payload)

            return Quote(
                symbol=canonical_sym,
                ltp=ltp,
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=volume,
                change=ltp - close if ltp and close else Decimal("0"),
                bid=bid,
                ask=ask,
                timestamp=ts,
            )
        except (ValueError, KeyError, TypeError):
            logger.debug(
                "Upstox tick translation failed; forwarding raw payload",
                exc_info=True,
            )
            return raw

    @staticmethod
    def _extract_instrument_key(payload: Any) -> str:
        """Extract instrument_key from payload (dict or protobuf object)."""
        if isinstance(payload, dict):
            return payload.get("instrument_key") or payload.get("instrumentKey", "")
        return getattr(payload, "instrument_key", None) or getattr(payload, "instrumentKey", "")

    @staticmethod
    def _extract_price(payload: Any, field_names: list[str]) -> Decimal | None:
        """Extract a price field from payload, trying multiple field names."""
        for name in field_names:
            if isinstance(payload, dict):
                val = payload.get(name)
                if val is not None:
                    return Decimal(str(val))
            else:
                val = getattr(payload, name, None)
                if val is not None:
                    return Decimal(str(val))
        return Decimal("0")

    @staticmethod
    def _extract_int(payload: Any, field_name: str) -> int:
        """Extract an integer field from payload."""
        if isinstance(payload, dict):
            return int(payload.get(field_name, 0) or 0)
        return int(getattr(payload, field_name, 0) or 0)

    @staticmethod
    def _extract_ohlc(payload: Any) -> tuple[Decimal, Decimal, Decimal, Decimal | None]:
        """Extract OHLC values from payload.

        Returns:
            Tuple of (open, high, low, close) where close may override top-level close
        """
        ohlc = (
            payload.get("ohlc", {}) if isinstance(payload, dict) else getattr(payload, "ohlc", None)
        )

        if isinstance(ohlc, dict):
            open_ = Decimal(str(ohlc.get("open", 0) or 0))
            high = Decimal(str(ohlc.get("high", 0) or 0))
            low = Decimal(str(ohlc.get("low", 0) or 0))
            cl = Decimal(str(ohlc.get("close", 0) or 0))
            return open_, high, low, cl if cl else None
        elif ohlc is not None:
            open_ = Decimal(str(getattr(ohlc, "open", 0) or 0))
            high = Decimal(str(getattr(ohlc, "high", 0) or 0))
            low = Decimal(str(getattr(ohlc, "low", 0) or 0))
            cl = Decimal(str(getattr(ohlc, "close", 0) or 0))
            return open_, high, low, cl if cl else None
        else:
            open_ = TickTranslatorAdapter._extract_price(payload, ["open"])
            high = TickTranslatorAdapter._extract_price(payload, ["high"])
            low = TickTranslatorAdapter._extract_price(payload, ["low"])
            return open_, high, low, None

    @staticmethod
    def _extract_timestamp(payload: Any) -> datetime | None:
        """Extract and parse exchange_timestamp from payload."""
        try:
            ts_raw = (
                payload.get("exchange_timestamp")
                if isinstance(payload, dict)
                else getattr(payload, "exchange_timestamp", None)
            )
            if not ts_raw:
                return None

            if isinstance(ts_raw, int | float):
                return datetime.fromtimestamp(ts_raw / 1000, tz=timezone.utc)
            elif isinstance(ts_raw, str):
                return datetime.fromisoformat(ts_raw)
            else:
                return ts_raw
        except (ValueError, KeyError, TypeError):
            return None

    @staticmethod
    def _canonical_symbol_for_defn(
        defn: Any,
        fallback_key: str = "",
    ) -> str:
        """Derive a clean, user-facing canonical symbol from a definition.

        Priority:
        1. defn.name — long-form canonical name
        2. defn.symbol — trading symbol
        3. defn.trading_symbol
        4. RHS of instrument_key fallback
        """
        if defn is None:
            if fallback_key and "|" in fallback_key:
                return fallback_key.split("|", 1)[1]
            return fallback_key
        if defn.name:
            return defn.name
        if defn.symbol:
            return defn.symbol
        if defn.trading_symbol:
            return defn.trading_symbol
        if fallback_key and "|" in fallback_key:
            return fallback_key.split("|", 1)[1]
        return fallback_key

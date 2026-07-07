"""Upstox mapper — transforms raw Upstox JSON responses into domain entities.

Pure functions, no network calls. Every method is a @staticmethod that
takes a raw dict and returns a domain entity.

Upstox API JSON shapes (from archived code analysis):
- Orders: {"data": {"order_id": "...", "trading_symbol": "...", ...}}
- Positions: {"data": [{"trading_symbol": "...", "quantity": ..., ...}]}
- Balance: {"data": {"available_margin": ..., "used_margin": ..., ...}}
- Quote: {"data": {"NSE_EQ|INE002A01018": {"last_price": ..., "ohlc": {...}}}}
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from brokers.common.parsing import dec as _dec, int_val as _int, parse_ts as _parse_ts
from brokers.domain.enums import (
    Exchange,
    OrderStatus,
    OrderType,
    ProductType,
    Side,
    Validity,
)
from brokers.domain.order import Order
from brokers.domain.requests import OrderRequest
from brokers.domain.values import (
    Balance,
    DepthLevel,
    Holding,
    MarketDepth,
    Position,
    Quote,
    Trade,
)


# ── Segment to exchange mapping ─────────────────────────────────────────────

from brokers.common import segments as _segments


def _exchange_from_segment(segment: str) -> Exchange:
    return _segments.segment_to_exchange(segment)


# ── Product-type validation ────────────────────────────────────────────────────

_ALLOWED_PRODUCTS: dict[str, frozenset[str]] = {
    "NSE_EQ": frozenset({"I", "D", "MTF"}),
    "BSE_EQ": frozenset({"I", "D", "MTF"}),
    "NSE_FO": frozenset({"I"}),
    "BSE_FO": frozenset({"I"}),
    "MCX_FO": frozenset({"I"}),
    "NSE_CD": frozenset({"I"}),
    "BSE_CD": frozenset({"I"}),
}


def validate_product_type(segment: str, product_code: str) -> None:
    """Validate that product_code is allowed for the given Upstox segment.

    Raises:
        ValueError: If the combination is invalid per Upstox API rules.
    """
    allowed = _ALLOWED_PRODUCTS.get(segment)
    if allowed is None:
        return  # Unknown segment — skip validation
    if product_code not in allowed:
        raise ValueError(
            f"Product type {product_code!r} is not allowed for segment "
            f"{segment!r}. Allowed: {sorted(allowed)}"
        )


class UpstoxMapper:
    """Maps Upstox API JSON responses to domain entities."""

    # ── Order mapping ───────────────────────────────────────────────────────

    @staticmethod
    def map_order(raw: dict) -> Order:
        """Map an Upstox order dict to Order entity using from_broker_data factory."""
        segment = raw.get("segment", raw.get("exchange", "NSE_EQ"))
        return Order.from_broker_data(
            order_id=str(raw.get("order_id", raw.get("orderId", ""))),
            symbol=str(raw.get("trading_symbol", raw.get("tradingsymbol", ""))),
            exchange=_exchange_from_segment(segment),
            side=Side(str(raw.get("transaction_type", raw.get("side", "BUY"))).upper()),
            quantity=_int(raw.get("quantity", 0)),
            order_type=OrderType(str(raw.get("order_type", raw.get("ordertype", "MARKET"))).upper()),
            product_type=UpstoxMapper._map_product(str(raw.get("product", raw.get("product_type", "I"))).upper()),
            validity=Validity(str(raw.get("validity", "DAY")).upper()),
            price=_dec(raw.get("price", 0)),
            trigger_price=_dec(raw.get("trigger_price", 0)) or None,
            status=UpstoxMapper._map_status(str(raw.get("status", "open")).upper()),
            filled_quantity=_int(raw.get("filled_quantity", raw.get("filled_qty", 0))),
            average_price=_dec(raw.get("average_price", raw.get("avg_price", 0))),
            timestamp=_parse_ts(raw.get("order_timestamp", raw.get("created_at"))) or datetime.now(timezone.utc),
        )

    @staticmethod
    def _map_status(raw: str) -> OrderStatus:
        """Map Upstox status strings to OrderStatus enum."""
        mapping = {
            "OPEN": OrderStatus.OPEN,
            "PENDING": OrderStatus.OPEN,
            "QUEUED": OrderStatus.OPEN,
            "OPEN_PENDING": OrderStatus.OPEN,
            "MODIFY_PENDING": OrderStatus.OPEN,
            "CANCEL_PENDING": OrderStatus.OPEN,
            "TRIGGER_PENDING": OrderStatus.OPEN,
            "COMPLETE": OrderStatus.FILLED,
            "FILLED": OrderStatus.FILLED,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "CANCELED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.EXPIRED,
        }
        return mapping.get(raw, OrderStatus.UNKNOWN)

    @staticmethod
    def _map_product(raw: str) -> ProductType:
        """Map Upstox product codes to ProductType enum."""
        mapping = {
            "I": ProductType.INTRADAY,
            "D": ProductType.CNC,
            "M": ProductType.MARGIN,
            "MTF": ProductType.MTF,
            "INTRADAY": ProductType.INTRADAY,
            "CNC": ProductType.CNC,
            "MARGIN": ProductType.MARGIN,
        }
        return mapping.get(raw, ProductType.INTRADAY)

    @staticmethod
    def build_order_payload(request: OrderRequest, instrument_key: str) -> dict[str, Any]:
        """Build the Upstox V3 order placement payload from OrderRequest."""
        # Extract segment from instrument_key (format: "SEGMENT|security_id")
        segment = instrument_key.split("|")[0] if "|" in instrument_key else "NSE_EQ"
        # Upstox product codes: I=Intraday, D=CNC, MTF=MTF
        product_map = {
            ProductType.INTRADAY: "I",
            ProductType.CNC: "D",
            ProductType.MTF: "MTF",
        }
        product_code = product_map.get(request.product_type, "I")
        # Validate product type for segment
        validate_product_type(segment, product_code)
        payload: dict[str, Any] = {
            "instrument_token": instrument_key,
            "quantity": request.quantity,
            "transaction_type": request.side.value,
            "order_type": request.order_type.value,
            "product": product_code,
            "validity": request.validity.value,
            "disclosed_quantity": 0,
            "is_amo": False,
            "slice": False,
        }
        if request.price and request.price > 0:
            payload["price"] = float(request.price)
        if request.trigger_price and request.trigger_price > 0:
            payload["trigger_price"] = float(request.trigger_price)
        return payload

    # ── Trade mapping ───────────────────────────────────────────────────────

    @staticmethod
    def map_trade(raw: dict) -> Trade:
        """Map an Upstox trade dict to Trade entity."""
        return Trade(
            trade_id=str(raw.get("trade_id", raw.get("id", ""))),
            order_id=str(raw.get("order_id", "")),
            symbol=str(raw.get("trading_symbol", raw.get("tradingsymbol", ""))),
            exchange=_exchange_from_segment(raw.get("segment", raw.get("exchange", "NSE_EQ"))),
            side=Side(str(raw.get("transaction_type", "BUY")).upper()),
            quantity=_int(raw.get("quantity", raw.get("filled_qty", 0))),
            price=_dec(raw.get("average_price", raw.get("price", 0))),
            timestamp=_parse_ts(raw.get("trade_timestamp", raw.get("created_at"))),
            product_type=UpstoxMapper._map_product(str(raw.get("product", "I")).upper()),
        )

    # ── Position mapping ────────────────────────────────────────────────────

    @staticmethod
    def map_position(raw: dict) -> Position:
        """Map an Upstox position dict to Position entity."""
        return Position(
            symbol=str(raw.get("trading_symbol", raw.get("tradingsymbol", ""))),
            exchange=_exchange_from_segment(raw.get("segment", raw.get("exchange", "NSE_EQ"))),
            quantity=_int(raw.get("quantity", 0)),
            average_price=_dec(raw.get("average_price", raw.get("buy_price", 0))),
            ltp=_dec(raw.get("last_price", 0)),
            unrealized_pnl=_dec(raw.get("unrealized_pnl", 0)),
            realized_pnl=_dec(raw.get("realized_pnl", 0)),
            product_type=UpstoxMapper._map_product(str(raw.get("product", "I")).upper()),
        )

    # ── Holding mapping ─────────────────────────────────────────────────────

    @staticmethod
    def map_holding(raw: dict) -> Holding:
        """Map an Upstox holding dict to Holding entity."""
        qty = _int(raw.get("quantity", 0))
        avg_px = _dec(raw.get("average_price", raw.get("buy_price", 0)))
        ltp = _dec(raw.get("last_price", 0))
        pnl = _dec(raw.get("pnl", 0))
        if pnl == 0 and avg_px > 0 and ltp > 0:
            pnl = (ltp - avg_px) * qty
        return Holding(
            symbol=str(raw.get("trading_symbol", raw.get("tradingsymbol", ""))),
            exchange=_exchange_from_segment(raw.get("segment", raw.get("exchange", "NSE_EQ"))),
            quantity=qty,
            available_quantity=_int(raw.get("available_quantity", raw.get("t1_quantity", qty))),
            average_price=avg_px,
            ltp=ltp,
            pnl=pnl,
        )

    # ── Balance mapping ─────────────────────────────────────────────────────

    @staticmethod
    def map_balance(raw: dict) -> Balance:
        """Map an Upstox fund/margin dict to Balance entity."""
        return Balance(
            available_balance=_dec(raw.get("available_margin", raw.get("available_balance", 0))),
            used_margin=_dec(raw.get("used_margin", 0)),
            total_value=_dec(raw.get("total_margin", 0)),
            sod_limit=_dec(raw.get("sod_limit", raw.get("start_of_day_margin", 0))),
            collateral_amount=_dec(raw.get("collateral_amount", 0)),
            withdrawable_balance=_dec(raw.get("withdrawable_balance", 0)),
        )

    # ── Market data mapping ─────────────────────────────────────────────────

    @staticmethod
    def map_quote(raw: dict, symbol: str) -> Quote:
        """Map an Upstox quote response to Quote entity.

        Upstox returns nested data under instrument_key.
        The caller extracts the inner dict and passes it here.
        """
        ohlc = raw.get("ohlc", {}) or {}
        return Quote(
            symbol=symbol,
            ltp=_dec(raw.get("last_price", 0)),
            open=_dec(ohlc.get("open", 0)),
            high=_dec(ohlc.get("high", 0)),
            low=_dec(ohlc.get("low", 0)),
            close=_dec(ohlc.get("close", 0)),
            volume=_int(raw.get("volume", 0)),
            change=_dec(raw.get("net_change", 0)),
        )

    @staticmethod
    def map_depth(raw: dict, symbol: str) -> MarketDepth:
        """Map an Upstox depth response to MarketDepth entity."""
        depth = raw.get("depth", {}) or {}
        bids = [
            DepthLevel(
                price=_dec(b.get("price", 0)),
                quantity=_int(b.get("quantity", 0)),
                orders=_int(b.get("orders", 0)),
            )
            for b in (depth.get("bids", []) or [])[:5]
        ]
        asks = [
            DepthLevel(
                price=_dec(a.get("price", 0)),
                quantity=_int(a.get("quantity", 0)),
                orders=_int(a.get("orders", 0)),
            )
            for a in (depth.get("asks", []) or [])[:5]
        ]
        return MarketDepth(symbol=symbol, bids=bids, asks=asks, depth_type="DEPTH_5")

    # NOTE: Option/Future chain mapping removed — providers now parse
    # raw chain data into OptionContract/FutureContract lists directly,
    # bypassing dict intermediaries. See UpstoxProvider.get_option_chain.


__all__ = ["UpstoxMapper"]

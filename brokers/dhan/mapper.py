"""Dhan mapper — transforms raw Dhan JSON responses into domain entities.

Pure functions, no network calls. Every method is a @staticmethod that
takes a raw dict and returns a domain entity.

Dhan API JSON shapes (from archived code analysis):
- Orders: {"data": {"orderId": "...", "tradingSymbol": "...", ...}}
- Positions: {"data": [{"tradingSymbol": "...", "netQuantity": ..., ...}]}
- Balance: {"data": {"availabelBalance": ..., "sodLimit": ..., ...}}
- Quote: {"data": {"NSE_EQ": {"12345": {"last_price": ..., "ohlc": {...}}}}
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


# Alias kept for backward-compatible test references; delegates to the shared map.
_SEGMENT_TO_EXCHANGE = _segments.SEGMENT_TO_EXCHANGE


# ── Product-type validation per Dhan segment rules ──────────────────────────
# Per Dhan API:
#   NSE_EQ, BSE_EQ → CNC, INTRADAY, MARGIN, MTF
#   NSE_FNO, BSE_FNO, MCX_COMM, NSE_CURRENCY, BSE_CURRENCY → INTRADAY, MARGIN only

_ALLOWED_PRODUCTS: dict[str, frozenset[str]] = {
    "NSE_EQ": frozenset({"CNC", "INTRADAY", "MARGIN", "MTF"}),
    "BSE_EQ": frozenset({"CNC", "INTRADAY", "MARGIN", "MTF"}),
    "NSE_FNO": frozenset({"INTRADAY", "MARGIN"}),
    "BSE_FNO": frozenset({"INTRADAY", "MARGIN"}),
    "MCX_COMM": frozenset({"INTRADAY", "MARGIN"}),
    "NSE_CURRENCY": frozenset({"INTRADAY", "MARGIN"}),
    "BSE_CURRENCY": frozenset({"INTRADAY", "MARGIN"}),
}


def validate_product_type(segment: str, product_type: str) -> None:
    """Validate that product_type is allowed for the given Dhan segment.

    Raises:
        ValueError: If the combination is invalid per Dhan API rules.
    """
    allowed = _ALLOWED_PRODUCTS.get(segment)
    if allowed is None:
        return  # Unknown segment — skip validation
    if product_type not in allowed:
        raise ValueError(
            f"Product type {product_type!r} is not allowed for segment "
            f"{segment!r}. Allowed: {sorted(allowed)}"
        )


class DhanMapper:
    """Maps Dhan API JSON responses to domain entities."""

    # ── Order mapping ───────────────────────────────────────────────────────

    @staticmethod
    def map_order(raw: dict) -> Order:
        """Map a Dhan order dict to Order entity using from_broker_data factory."""
        segment = raw.get("exchangeSegment", "NSE_EQ")
        return Order.from_broker_data(
            order_id=str(raw.get("orderId", "")),
            symbol=str(raw.get("tradingSymbol", "")),
            exchange=_exchange_from_segment(segment),
            side=Side(str(raw.get("transactionType", "BUY")).upper()),
            quantity=_int(raw.get("quantity", 0)),
            order_type=OrderType(str(raw.get("orderType", "MARKET")).upper()),
            product_type=ProductType(str(raw.get("productType", "INTRADAY")).upper()),
            validity=Validity(str(raw.get("validity", "DAY")).upper()),
            price=_dec(raw.get("price", 0)),
            trigger_price=_dec(raw.get("triggerPrice", 0)) or None,
            status=DhanMapper._map_status(str(raw.get("orderStatus", "PENDING")).upper()),
            filled_quantity=_int(raw.get("filledQty", 0)),
            average_price=_dec(raw.get("avgPrice", 0)),
            correlation_id=raw.get("correlationId"),
            timestamp=_parse_ts(raw.get("createdAt", raw.get("orderTime"))) or datetime.now(timezone.utc),
        )

    @staticmethod
    def _map_status(raw: str) -> OrderStatus:
        """Map Dhan status strings to OrderStatus enum."""
        from brokers.dhan.status_mapping import to_order_status
        return to_order_status(raw)

    @staticmethod
    def build_order_payload(
        request: OrderRequest,
        security_id: str,
        segment: str,
        client_id: str,
    ) -> dict[str, Any]:
        """Build the Dhan order placement payload from OrderRequest."""
        validate_product_type(segment, request.product_type.value)
        payload: dict[str, Any] = {
            "dhanClientId": client_id,
            "securityId": security_id,
            "exchangeSegment": segment,
            "transactionType": request.side.value,
            "orderType": request.order_type.value,
            "productType": request.product_type.value,
            "validity": request.validity.value,
            "quantity": request.quantity,
        }
        if request.price and request.price > 0:
            payload["price"] = float(request.price)
        if request.trigger_price and request.trigger_price > 0:
            payload["triggerPrice"] = float(request.trigger_price)
        return payload

    # ── Trade mapping ───────────────────────────────────────────────────────

    @staticmethod
    def map_trade(raw: dict) -> Trade:
        """Map a Dhan trade dict to Trade entity."""
        return Trade(
            trade_id=str(raw.get("tradeId", raw.get("id", ""))),
            order_id=str(raw.get("orderId", "")),
            symbol=str(raw.get("tradingSymbol", raw.get("symbol", ""))),
            exchange=_exchange_from_segment(raw.get("exchangeSegment", "NSE_EQ")),
            side=Side(str(raw.get("transactionType", "BUY")).upper()),
            quantity=_int(raw.get("tradedQty", raw.get("quantity", 0))),
            price=_dec(raw.get("tradedPrice", raw.get("price", 0))),
            timestamp=_parse_ts(raw.get("tradedTime", raw.get("createdAt"))),
            product_type=ProductType(str(raw.get("productType", "INTRADAY")).upper()),
        )

    # ── Position mapping ────────────────────────────────────────────────────

    @staticmethod
    def map_position(raw: dict) -> Position:
        """Map a Dhan position dict to Position entity."""
        return Position(
            symbol=str(raw.get("tradingSymbol", "")),
            exchange=_exchange_from_segment(raw.get("exchangeSegment", "NSE_EQ")),
            quantity=_int(raw.get("netQty", raw.get("netQuantity", 0))),
            average_price=_dec(raw.get("buyAvg", raw.get("buyAveragePrice", 0))),
            ltp=_dec(raw.get("lastPrice", 0)),
            unrealized_pnl=_dec(raw.get("unrealizedProfit", raw.get("unrealizedPnl", 0))),
            realized_pnl=_dec(raw.get("realizedProfit", raw.get("realizedPnl", 0))),
            product_type=ProductType(str(raw.get("productType", "INTRADAY")).upper()),
        )

    # ── Holding mapping ─────────────────────────────────────────────────────

    @staticmethod
    def map_holding(raw: dict) -> Holding:
        """Map a Dhan holding dict to Holding entity."""
        qty = _int(raw.get("totalQty", raw.get("quantity", 0)))
        avg_px = _dec(raw.get("avgCostPrice", raw.get("costPrice", 0)))
        ltp = _dec(raw.get("lastTradedPrice", raw.get("lastPrice", 0)))
        pnl_raw = raw.get("pnlValue")
        pnl = _dec(pnl_raw) if pnl_raw is not None else (
            (ltp - avg_px) * qty if avg_px > 0 and ltp > 0 else Decimal("0")
        )
        return Holding(
            symbol=str(raw.get("tradingSymbol", "")),
            exchange=_exchange_from_segment(raw.get("exchangeSegment", "NSE_EQ")),
            quantity=qty,
            available_quantity=_int(raw.get("availableQty", raw.get("availableQuantity", 0))),
            average_price=avg_px,
            ltp=ltp,
            pnl=pnl,
        )

    # ── Balance mapping ─────────────────────────────────────────────────────

    @staticmethod
    def map_balance(raw: dict) -> Balance:
        """Map a Dhan fundlimit dict to Balance entity."""
        return Balance(
            available_balance=_dec(raw.get("availabelBalance", raw.get("availableBalance", 0))),
            used_margin=_dec(raw.get("utilizedAmount", 0)),
            total_value=_dec(raw.get("sodLimit", 0)),
            sod_limit=_dec(raw.get("sodLimit", 0)),
            collateral_amount=_dec(raw.get("collateralAmount", 0)),
            withdrawable_balance=_dec(raw.get("withdrawableBalance", 0)),
        )

    # ── Market data mapping ─────────────────────────────────────────────────

    @staticmethod
    def map_quote(raw: dict, symbol: str) -> Quote:
        """Map a Dhan quote response to Quote entity.

        Dhan returns: {"data": {"NSE_EQ": {"12345": {"last_price": ..., "ohlc": {...}}}}
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
        """Map a Dhan depth response to MarketDepth entity."""
        depth = raw.get("depth", {}) or {}
        bids = [
            DepthLevel(
                price=_dec(level.get("price", 0)),
                quantity=_int(level.get("quantity", 0)),
                orders=_int(level.get("orders", 0)),
            )
            for level in (depth.get("buy", []) or [])[:5]
        ]
        asks = [
            DepthLevel(
                price=_dec(level.get("price", 0)),
                quantity=_int(level.get("quantity", 0)),
                orders=_int(level.get("orders", 0)),
            )
            for level in (depth.get("sell", []) or [])[:5]
        ]
        return MarketDepth(symbol=symbol, bids=bids, asks=asks, depth_type="DEPTH_5")

    # NOTE: Option/Future chain mapping removed — providers now parse
    # raw chain data into OptionContract/FutureContract lists directly,
    # bypassing dict intermediaries. See DhanProvider.get_option_chain.


__all__ = ["DhanMapper"]

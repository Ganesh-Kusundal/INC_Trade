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

_SEGMENT_TO_EXCHANGE: dict[str, Exchange] = {
    "NSE_EQ": Exchange.NSE,
    "BSE_EQ": Exchange.BSE,
    "NSE_FNO": Exchange.NFO,
    "BSE_FNO": Exchange.NFO,
    "MCX_COMM": Exchange.MCX,
    "NSE_CURRENCY": Exchange.NFO,
    "BSE_CURRENCY": Exchange.NFO,
    "IDX_I": Exchange.INDEX,
}


def _exchange_from_segment(segment: str) -> Exchange:
    return _SEGMENT_TO_EXCHANGE.get(segment, Exchange.NSE)


def _dec(val: Any) -> Decimal:
    if val is None or val == "":
        return Decimal("0")
    try:
        return Decimal(str(val))
    except (ValueError, TypeError):
        return Decimal("0")


def _int(val: Any) -> int:
    if val is None or val == "":
        return 0
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0


def _parse_ts(val: Any) -> datetime | None:
    if val is None or val == "":
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except (ValueError, TypeError):
        return None


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
        mapping = {
            "PENDING": OrderStatus.OPEN,
            "TRANSIT": OrderStatus.OPEN,
            "PENDING_ORDER": OrderStatus.OPEN,
            "VALIDATED": OrderStatus.OPEN,
            "AMO_RECEIVED": OrderStatus.OPEN,
            "FILLED": OrderStatus.FILLED,
            "PART_FILLED": OrderStatus.PARTIALLY_FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "CANCELED": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
            "EXPIRED": OrderStatus.EXPIRED,
        }
        return mapping.get(raw, OrderStatus.UNKNOWN)

    @staticmethod
    def build_order_payload(
        request: OrderRequest,
        security_id: str,
        segment: str,
        client_id: str,
    ) -> dict[str, Any]:
        """Build the Dhan order placement payload from OrderRequest."""
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
            quantity=_int(raw.get("netQuantity", 0)),
            average_price=_dec(raw.get("buyAveragePrice", 0)),
            ltp=_dec(raw.get("lastPrice", 0)),
            unrealized_pnl=_dec(raw.get("unrealizedPnl", 0)),
            realized_pnl=_dec(raw.get("realizedPnl", 0)),
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

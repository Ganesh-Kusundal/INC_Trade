"""Upstox <-> Trade_XV2 domain mapper.

Mirrors Trade_J ``UpstoxDomainMapper``: maps between Upstox REST payloads and
the common ``OrderRequest`` (Pydantic) input model and canonical domain
dataclasses (``Order``/``Quote``/``Position``/etc.), normalises status strings,
and converts wire product / validity / order-type enums to the canonical
Trade_XV2 domain enums.

Provider metadata keys
----------------------
The ``BrokerOrderPayload.provider_metadata`` dict carries Upstox-specific
fields that have no canonical domain equivalent. The keys are centralised
here so adapters reference these constants rather than hardcoded strings::

    payload["is_amo"] = provider_metadata.get(PROVIDER_IS_AMO, False)
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Any

from domain import (
    DepthLevel,
    ExchangeSegment,
    FundLimits,
    HistoricalCandle,
    Holding,
    InstrumentType,
    MarketDepth,
    OptionContract,
    Order,
    OrderRequest,
    OrderResponse,
    OrderStatus,
    OrderType,
    Position,
    ProductType,
    Quote,
    Side,
    Trade,
    Validity,
)
from domain.parsing import (
    parse_decimal,
    parse_int,
    parse_optional_str,
    parse_timestamp,
)
from domain.status_mapper import StatusMapperRegistry, UnmappedBrokerStatusError

from .price_parser import UpstoxPriceParser

# ── Provider metadata key constants ──────────────────────────────────────
# These keys are used by Upstox adapters to read/write broker-specific
# fields in ``BrokerOrderPayload.provider_metadata``. Centralising them
# here eliminates hardcoded string literals scattered across the codebase.
PROVIDER_IS_AMO: str = "is_amo"
PROVIDER_MARKET_PROTECTION: str = "market_protection"
PROVIDER_ALGO_NAME: str = "algo_name"

_PRODUCT_TO_WIRE = {
    ProductType.INTRADAY: "I",
    ProductType.CNC: "D",
    ProductType.MARGIN: "M",
    ProductType.MTF: "MTF",
}
_WIRE_TO_PRODUCT = {v: k for k, v in _PRODUCT_TO_WIRE.items() if v not in ("D",)}

_VALIDITY_TO_WIRE = {
    Validity.DAY: "DAY",
    Validity.IOC: "IOC",
}
_WIRE_TO_VALIDITY = {v: k for k, v in _VALIDITY_TO_WIRE.items()}

_ORDER_TYPE_TO_WIRE = {
    OrderType.MARKET: "MARKET",
    OrderType.LIMIT: "LIMIT",
    OrderType.STOP_LOSS: "SL",
    OrderType.STOP_LOSS_MARKET: "SL-M",
}
_WIRE_TO_ORDER_TYPE = {v: k for k, v in _ORDER_TYPE_TO_WIRE.items()}

_TXN_TO_WIRE = {
    Side.BUY: "BUY",
    Side.SELL: "SELL",
}
_WIRE_TO_TXN = {v: k for k, v in _TXN_TO_WIRE.items()}


def _wire_status_to_domain_status(raw: str) -> OrderStatus:
    """Convert Upstox wire status string to canonical domain OrderStatus.

    Uses strict status mapping to ensure unmapped statuses raise errors
    instead of silently defaulting to UNKNOWN or OPEN.
    """
    if not raw:
        # Empty status is a special case - we default to OPEN for backward compatibility
        # but this should be investigated as it might indicate missing data
        return OrderStatus.OPEN
    return StatusMapperRegistry.normalize_strict(raw)


# ── Parsing helpers (delegated to shared utilities) ─────────────────────

_str_or_none = parse_optional_str
_to_decimal = parse_decimal
_to_int = parse_int
_parse_iso = parse_timestamp


class UpstoxDomainMapper:
    """Static, side-effect-free converters between Upstox wire payloads and
    Trade_XV2 canonical domain dataclasses.
    """

    @staticmethod
    def normalize_status(raw_status: str) -> OrderStatus:
        return _wire_status_to_domain_status(raw_status)

    @staticmethod
    def product_to_wire(product: ProductType) -> str:
        return _PRODUCT_TO_WIRE.get(product, "I")

    @staticmethod
    def product_from_wire(raw: str) -> ProductType:
        raw = (raw or "").upper()
        if raw in ("D", "DELIVERY"):
            return ProductType.CNC
        if raw in ("I", "INTRADAY", "MIS"):
            return ProductType.INTRADAY
        if raw in ("M", "MARGIN"):
            return ProductType.MARGIN
        if raw in ("MTF",):
            return ProductType.MTF
        return ProductType.INTRADAY

    @staticmethod
    def validity_to_wire(validity: Validity) -> str:
        return _VALIDITY_TO_WIRE.get(validity, "DAY")

    @staticmethod
    def validity_from_wire(raw: str) -> Validity:
        raw = (raw or "").upper()
        return _WIRE_TO_VALIDITY.get(raw, Validity.DAY)

    @staticmethod
    def order_type_to_wire(order_type: OrderType) -> str:
        return _ORDER_TYPE_TO_WIRE.get(order_type, "MARKET")

    @staticmethod
    def order_type_from_wire(raw: str) -> OrderType:
        raw = (raw or "").upper()
        if raw in ("MARKET", "MKT"):
            return OrderType.MARKET
        if raw in ("LIMIT", "LMT"):
            return OrderType.LIMIT
        if raw in ("SL", "STOP_LOSS", "STOPLOSS"):
            return OrderType.STOP_LOSS
        if raw in ("SL-M", "SLM", "STOP_LOSS_MARKET", "STOPLOSS_MARKET"):
            return OrderType.STOP_LOSS_MARKET
        return OrderType.MARKET

    @staticmethod
    def txn_to_wire(txn: Side) -> str:
        return _TXN_TO_WIRE.get(txn, "BUY")

    @staticmethod
    def txn_from_wire(raw: str) -> Side:
        raw = (raw or "").upper()
        return _WIRE_TO_TXN.get(raw, Side.BUY)

    @staticmethod
    def segment_from_wire(segment: str) -> ExchangeSegment:
        from brokers.upstox.instruments.segment_mapper import UpstoxSegmentMapper

        return UpstoxSegmentMapper.to_safe(segment)

    @staticmethod
    def segment_to_wire(segment: ExchangeSegment) -> str:
        from brokers.upstox.instruments.segment_mapper import UpstoxSegmentMapper

        return UpstoxSegmentMapper.to_wire(segment)

    @staticmethod
    def instrument_type_from_wire(raw: str) -> InstrumentType:
        raw = (raw or "").upper()
        if raw in ("EQ", "EQUITY", "STOCK"):
            return InstrumentType.EQUITY
        if raw in ("FUT", "FUTURE", "FUTURES"):
            return InstrumentType.FUTURES
        if raw in ("OPT", "OPTION", "OPTIONS"):
            return InstrumentType.OPTIONS
        if raw in ("IDX", "INDEX"):
            return InstrumentType.INDEX
        if raw in ("COM", "COMMODITY"):
            return InstrumentType.COMMODITY
        if raw in ("CUR", "CURRENCY"):
            return InstrumentType.CURRENCY
        return InstrumentType.EQUITY

    @staticmethod
    def to_place_payload(
        request: OrderRequest,
        instrument_key: str,
        *,
        algo_name: str | None = None,
        market_protection: int | None = None,
        slice_orders: bool = False,
    ) -> dict[str, Any]:
        provider_metadata = getattr(request, "provider_metadata", {}) or {}
        is_market = request.order_type == OrderType.MARKET
        from domain.utils.price import to_wire_float

        price_value = (
            0
            if is_market
            else (
                to_wire_float(request.price)
                if request.price and request.price > 0
                else 0
            )
        )
        payload: dict[str, Any] = {
            "quantity": request.quantity,
            "product": UpstoxDomainMapper.product_to_wire(request.product_type),
            "validity": UpstoxDomainMapper.validity_to_wire(request.validity),
            "price": price_value,
            "instrument_token": instrument_key,
            "order_type": UpstoxDomainMapper.order_type_to_wire(request.order_type),
            "transaction_type": UpstoxDomainMapper.txn_to_wire(request.transaction_type),
            "disclosed_quantity": int(getattr(request, "disclosed_quantity", 0) or 0),
            "trigger_price": to_wire_float(request.trigger_price)
            if request.trigger_price
            else 0,
            PROVIDER_IS_AMO: bool(provider_metadata.get(PROVIDER_IS_AMO, False)),
        }
        tag = request.correlation_id or request.tag
        if tag:
            payload["tag"] = str(tag)[:40]
        if getattr(request, "slice", False) or slice_orders:
            payload["slice"] = True
        mp = market_protection
        if mp is None:
            mp = provider_metadata.get(PROVIDER_MARKET_PROTECTION, -1)
        payload[PROVIDER_MARKET_PROTECTION] = int(mp) if mp is not None else -1
        if algo_name:
            payload.setdefault(PROVIDER_ALGO_NAME, algo_name)
        return payload

    @staticmethod
    def to_modify_payload(
        order_id: str,
        instrument_key: str,
        *,
        quantity: int | None = None,
        price: Decimal | None = None,
        trigger_price: Decimal | None = None,
        order_type: OrderType | None = None,
        validity: Validity | None = None,
        market_protection: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "order_id": order_id,
            "instrument_token": instrument_key,
        }
        if quantity is not None:
            payload["quantity"] = int(quantity)
        if price is not None:
            from domain.utils.price import to_wire_float

            payload["price"] = to_wire_float(price)
        if trigger_price is not None:
            from domain.utils.price import to_wire_float

            payload["trigger_price"] = to_wire_float(trigger_price)
        if order_type is not None:
            payload["order_type"] = UpstoxDomainMapper.order_type_to_wire(order_type)
        if validity is not None:
            payload["validity"] = UpstoxDomainMapper.validity_to_wire(validity)
        if market_protection is not None:
            payload["market_protection"] = int(market_protection)
        return payload

    @staticmethod
    def to_order_response(payload: Any) -> OrderResponse:
        if not isinstance(payload, dict):
            return OrderResponse.fail("Order failed: unexpected response")
        errors = payload.get("errors")
        if errors:
            first = errors[0] if isinstance(errors, list) and errors else {}
            if isinstance(first, dict):
                message = first.get("message") or first.get("error") or str(first)
            else:
                message = str(first)
            return OrderResponse.fail(message)
        data = payload.get("data")
        if isinstance(data, dict):
            order_id = str(data.get("order_id") or payload.get("order_id") or "")
        else:
            order_id = str(payload.get("order_id") or "")
        if not order_id:
            remarks = payload.get("remarks") or payload.get("message") or "Order failed"
            return OrderResponse.fail(remarks)

        # Extract and normalize status from payload
        status_str = str(data.get("status") or payload.get("status") or "")
        try:
            status = UpstoxDomainMapper.normalize_status(status_str) if status_str else OrderStatus.OPEN
        except UnmappedBrokerStatusError as exc:
            # Log the unmapped status but don't fail the order response
            # This allows the order to proceed while flagging the issue for investigation
            logger = logging.getLogger(__name__)
            logger.error(
                "unmapped_order_status_in_response",
                extra={
                    "order_id": order_id,
                    "raw_status": status_str,
                    "error": str(exc)
                }
            )
            # Default to OPEN but this should be investigated
            status = OrderStatus.OPEN

        return OrderResponse.ok(
            order_id=order_id,
            message=str(data) if data is not None else "",
            status=status
        )

    @staticmethod
    def to_quote(payload: Any) -> Quote:
        if not isinstance(payload, dict):
            return Quote(symbol="")
        data = payload.get("data") if "data" in payload else payload
        if not isinstance(data, dict):
            data = {}
        # Handle nested key structure: {"data": {"NSE_EQ|RELIANCE": {...}}}
        if data and "symbol" not in data and "last_price" not in data and "ltp" not in data:
            for _key, value in data.items():
                if isinstance(value, dict) and (
                    "last_price" in value or "ltp" in value or "symbol" in value
                ):
                    data = value
                    break
        ohlc = data.get("ohlc") or {}
        depth = data.get("depth") or {}
        bid = depth.get("buy") if isinstance(depth, dict) else None
        ask = depth.get("sell") if isinstance(depth, dict) else None
        return Quote(
            symbol=str(data.get("symbol") or data.get("trading_symbol") or ""),
            ltp=UpstoxPriceParser.parse(data.get("last_price") or data.get("ltp") or 0),
            open=UpstoxPriceParser.parse(ohlc.get("open") or 0),
            high=UpstoxPriceParser.parse(ohlc.get("high") or 0),
            low=UpstoxPriceParser.parse(ohlc.get("low") or 0),
            close=UpstoxPriceParser.parse(ohlc.get("close") or 0),
            volume=_to_int(data.get("volume")),
            bid=UpstoxPriceParser.parse(bid[0].get("price"))
            if isinstance(bid, list) and bid
            else None,
            ask=UpstoxPriceParser.parse(ask[0].get("price"))
            if isinstance(ask, list) and ask
            else None,
            change=UpstoxPriceParser.parse(data.get("change") or 0),
            timestamp=_parse_iso(data.get("timestamp") or data.get("last_trade_time")),
        )

    @staticmethod
    def to_position(payload: Any) -> Position:
        if not isinstance(payload, dict):
            return Position(symbol="")
        return Position(
            symbol=str(payload.get("trading_symbol") or payload.get("symbol") or ""),
            exchange=str(payload.get("exchange") or ""),
            quantity=_to_int(payload.get("net_quantity") or payload.get("quantity")),
            avg_price=UpstoxPriceParser.parse(payload.get("buy_average_price") or 0),
            ltp=UpstoxPriceParser.parse(payload.get("last_price") or 0),
            unrealized_pnl=UpstoxPriceParser.parse(payload.get("unrealised") or 0),
            realized_pnl=UpstoxPriceParser.parse(payload.get("realised") or 0),
            product_type=UpstoxDomainMapper.product_from_wire(str(payload.get("product") or "I")),
        )

    @staticmethod
    def to_holding(payload: Any) -> Holding:
        if not isinstance(payload, dict):
            return Holding(symbol="")
        return Holding(
            symbol=str(payload.get("trading_symbol") or payload.get("symbol") or ""),
            exchange=str(payload.get("exchange") or ""),
            quantity=_to_int(payload.get("quantity")),
            available_quantity=_to_int(payload.get("quantity")),
            avg_price=UpstoxPriceParser.parse(payload.get("average_price") or 0),
            ltp=UpstoxPriceParser.parse(payload.get("last_price") or 0),
            pnl=UpstoxPriceParser.parse(payload.get("pnl") or 0),
        )

    @staticmethod
    def to_trade(payload: Any) -> Trade:
        if not isinstance(payload, dict):
            return Trade(
                trade_id="", order_id="", symbol="", exchange="", side=Side.BUY, quantity=0
            )
        return Trade(
            trade_id=str(payload.get("trade_id") or ""),
            order_id=str(payload.get("order_id") or ""),
            symbol=str(payload.get("trading_symbol") or payload.get("symbol") or ""),
            exchange=str(payload.get("exchange") or ""),
            side=UpstoxDomainMapper.txn_from_wire(str(payload.get("transaction_type") or "BUY")),
            quantity=_to_int(payload.get("quantity") or payload.get("traded_quantity")),
            price=UpstoxPriceParser.parse(
                payload.get("price") or payload.get("average_price") or 0
            ),
            trade_value=UpstoxPriceParser.parse(
                (payload.get("price") or 0) * (payload.get("quantity") or 0)
            ),
            timestamp=_parse_iso(payload.get("trade_time") or payload.get("timestamp")),
            product_type=UpstoxDomainMapper.product_from_wire(str(payload.get("product") or "I")),
        )

    @staticmethod
    def to_fund_limits(payload: Any) -> FundLimits:
        if not isinstance(payload, dict):
            return FundLimits()
        data = payload.get("data") if "data" in payload else payload
        if not isinstance(data, dict):
            return FundLimits()
        equity = data.get("equity") or {}
        return FundLimits(
            available_balance=UpstoxPriceParser.parse(
                equity.get("available_margin") or data.get("available_margin") or 0
            ),
            used_margin=UpstoxPriceParser.parse(
                equity.get("used_margin") or data.get("used_margin") or 0
            ),
            total_margin=UpstoxPriceParser.parse(
                equity.get("net_margin") or data.get("net_margin") or 0
            ),
        )

    @staticmethod
    def to_option_contract(payload: Any) -> OptionContract:
        if not isinstance(payload, dict):
            return OptionContract()
        call = payload.get("call_options") if isinstance(payload.get("call_options"), dict) else {}
        put = payload.get("put_options") if isinstance(payload.get("put_options"), dict) else {}

        return OptionContract(
            strike=UpstoxPriceParser.parse(payload.get("strike_price") or 0),
            expiry=str(payload.get("expiry") or ""),
            instrument_type=UpstoxDomainMapper.instrument_type_from_wire(
                str(payload.get("instrument_type") or "")
            ).value,
            exchange=str(payload.get("exchange") or "NFO"),
            lot_size=_to_int(payload.get("lot_size")),
            call_ltp=UpstoxDomainMapper._leg_ltp(call),
            call_oi=UpstoxDomainMapper._leg_oi(call),
            call_volume=UpstoxDomainMapper._leg_volume(call),
            call_iv=UpstoxDomainMapper._leg_iv(call),
            put_ltp=UpstoxDomainMapper._leg_ltp(put),
            put_oi=UpstoxDomainMapper._leg_oi(put),
            put_volume=UpstoxDomainMapper._leg_volume(put),
            put_iv=UpstoxDomainMapper._leg_iv(put),
        )

    # -- Per-leg field extractors for Upstox option-chain payloads ---------
    @staticmethod
    def _leg_market_data(leg: dict) -> dict:
        if not isinstance(leg, dict):
            return {}
        md = leg.get("market_data")
        return md if isinstance(md, dict) else {}

    @staticmethod
    def _leg_greeks(leg: dict) -> dict:
        if not isinstance(leg, dict):
            return {}
        g = leg.get("option_greeks")
        return g if isinstance(g, dict) else {}

    @staticmethod
    def _leg_ltp(leg: dict):
        md = UpstoxDomainMapper._leg_market_data(leg)
        val = md.get("ltp")
        return UpstoxPriceParser.parse(val) if val is not None else None

    @staticmethod
    def _leg_oi(leg: dict) -> int | None:
        md = UpstoxDomainMapper._leg_market_data(leg)
        val = md.get("oi")
        return _to_int(val) if val is not None else None

    @staticmethod
    def _leg_volume(leg: dict) -> int | None:
        md = UpstoxDomainMapper._leg_market_data(leg)
        val = md.get("volume")
        return _to_int(val) if val is not None else None

    @staticmethod
    def _leg_iv(leg: dict):
        md = UpstoxDomainMapper._leg_market_data(leg)
        val = md.get("iv")
        return UpstoxPriceParser.parse(val) if val is not None else None

    @staticmethod
    def leg_instrument_key(leg: dict) -> str | None:
        if not isinstance(leg, dict):
            return None
        key = leg.get("instrument_key") or leg.get("instrument_token")
        return str(key) if key else None

    @staticmethod
    def leg_trading_symbol(leg: dict) -> str | None:
        if not isinstance(leg, dict):
            return None
        ts = leg.get("trading_symbol") or leg.get("symbol")
        return str(ts) if ts else None

    @staticmethod
    def to_historical_candle(payload: Any) -> HistoricalCandle:
        if not isinstance(payload, dict):
            return HistoricalCandle()
        return HistoricalCandle(
            timestamp=_parse_iso(payload.get("timestamp") or payload.get("time")) or datetime.now(),
            open=UpstoxPriceParser.parse(payload.get("open") or 0),
            high=UpstoxPriceParser.parse(payload.get("high") or 0),
            low=UpstoxPriceParser.parse(payload.get("low") or 0),
            close=UpstoxPriceParser.parse(payload.get("close") or 0),
            volume=_to_int(payload.get("volume")),
        )

    @staticmethod
    def to_historical_candles(payload: Any) -> list[HistoricalCandle]:
        candles: list[HistoricalCandle] = []
        if not isinstance(payload, dict):
            return candles
        data = payload.get("data") or payload
        if isinstance(data, dict):
            rows = data.get("candles") or data.get("data") or []
        else:
            rows = data or payload.get("candles") or []
        if not isinstance(rows, list):
            return candles
        for row in rows:
            if isinstance(row, list) and len(row) >= 5:
                candles.append(
                    HistoricalCandle(
                        timestamp=_parse_iso(row[0]) or datetime.now(),
                        open=UpstoxPriceParser.parse(row[1]),
                        high=UpstoxPriceParser.parse(row[2]),
                        low=UpstoxPriceParser.parse(row[3]),
                        close=UpstoxPriceParser.parse(row[4]),
                        volume=_to_int(row[5]) if len(row) > 5 else 0,
                    )
                )
            elif isinstance(row, dict):
                candles.append(UpstoxDomainMapper.to_historical_candle(row))
        return candles

    @staticmethod
    def to_market_depth(payload: Any) -> MarketDepth:
        if not isinstance(payload, dict):
            return MarketDepth()
        data = payload.get("data") if "data" in payload else payload
        if not isinstance(data, dict):
            return MarketDepth()
        # Handle nested key structure: {"data": {"NSE_EQ:RELIANCE": {"depth": {...}}}}
        # or flat structure: {"depth": {...}}
        depth = data.get("depth")
        if depth is None:
            # Try to find depth in nested keys
            for _key, value in data.items():
                if isinstance(value, dict) and "depth" in value:
                    depth = value.get("depth", {})
                    break
        depth = depth or {}
        bids = depth.get("buy") or []
        asks = depth.get("sell") or []

        def _to_levels(rows):
            out = []
            for row in rows or []:
                if not isinstance(row, dict):
                    continue
                out.append(
                    DepthLevel(
                        price=UpstoxPriceParser.parse(row.get("price") or 0),
                        quantity=_to_int(row.get("quantity")),
                        orders=_to_int(row.get("orders")),
                    )
                )
            return out

        return MarketDepth(
            bids=_to_levels(bids),
            asks=_to_levels(asks),
        )

    @staticmethod
    def to_order(payload: Any) -> Order:
        if not isinstance(payload, dict):
            return Order(
                order_id="",
                symbol="",
                exchange="",
                side=Side.BUY,
                order_type=OrderType.MARKET,
                quantity=0,
            )
        return Order(
            order_id=str(payload.get("order_id") or ""),
            correlation_id=_str_or_none(payload.get("tag")),
            symbol=str(payload.get("trading_symbol") or payload.get("symbol") or ""),
            exchange=str(payload.get("exchange") or ""),
            side=UpstoxDomainMapper.txn_from_wire(str(payload.get("transaction_type") or "BUY")),
            quantity=_to_int(payload.get("quantity")),
            price=UpstoxPriceParser.parse(payload.get("price") or 0),
            trigger_price=UpstoxPriceParser.parse(payload.get("trigger_price") or 0),
            order_type=UpstoxDomainMapper.order_type_from_wire(
                str(payload.get("order_type") or "MARKET")
            ),
            product_type=UpstoxDomainMapper.product_from_wire(str(payload.get("product") or "I")),
            validity=UpstoxDomainMapper.validity_from_wire(str(payload.get("validity") or "DAY")),
            status=UpstoxDomainMapper.normalize_status(str(payload.get("status") or "")),
            filled_quantity=_to_int(payload.get("filled_quantity")),
            avg_price=UpstoxPriceParser.parse(payload.get("average_price") or 0),
            timestamp=_parse_iso(payload.get("order_timestamp")),
            reject_reason=_str_or_none(
                payload.get("status_message") or payload.get("rejection_reason")
            )
            or "",
        )

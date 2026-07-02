"""Market data adapter — LTP, Quote, Depth, OHLC."""

from __future__ import annotations

import logging
from decimal import Decimal

from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.identity import DhanIdentityProvider, coerce_identity_provider
from brokers.dhan.invariants import assert_dhan_identity
from domain import DepthLevel, MarketDepth, Quote

logger = logging.getLogger(__name__)


class MarketDataAdapter:
    def __init__(self, client: DhanHttpClient, identity: DhanIdentityProvider | object):
        self._client = client
        self._identity = coerce_identity_provider(identity)
        self._resolver = self._identity.resolver

    def _resolve_and_segment(self, symbol: str, exchange: str):
        """Resolve *symbol* on *exchange* and return (ref, segment).

        Uses the identity provider so the carrier (DhanInstrumentRef) is
        the only thing that can flow into a Dhan HTTP body. The provider
        enforces the Dhan-internal contract on every call.
        """
        ref = self._identity.resolve_ref(symbol, exchange)
        return ref, ref.exchange_segment

    def get_ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        ref, segment = self._resolve_and_segment(symbol, exchange)
        sid = int(ref.security_id)
        # PR-B: defence-in-depth invariant assertion. The market-feed
        # endpoint takes a ``{segment: [security_id, ...]}`` map rather
        # than a flat payload, so we verify each entry with
        # ``assert_dhan_identity`` rather than ``assert_dhan_payload``.
        assert_dhan_identity(sid, segment, context="market_data.get_ltp")
        data = self._client.post("/marketfeed/ltp", json={segment: [sid]})
        segment_data = data.get("data", {}).get(segment, {})
        entry = segment_data.get(str(sid))
        if entry is None:
            logger.warning(
                "ltp_missing_for_security_id",
                extra={
                    "symbol": symbol,
                    "security_id": sid,
                    "segment": segment,
                    "available_keys": list(segment_data.keys())[:5],
                },
            )
            raise ValueError(
                f"No LTP data for {symbol} on {exchange} (security_id={sid}, segment={segment})"
            )
        ltp = Decimal(str(entry["last_price"]))
        logger.debug("ltp_fetched", extra={"symbol": symbol, "ltp": str(ltp)})
        return ltp

    def get_quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        ref, segment = self._resolve_and_segment(symbol, exchange)
        sid = int(ref.security_id)
        assert_dhan_identity(sid, segment, context="market_data.get_quote")
        data = self._client.post("/marketfeed/quote", json={segment: [sid]})
        raw = data["data"][segment][str(sid)]
        ohlc = raw.get("ohlc", {}) or {}

        display = ref.symbol
        quote = Quote(
            symbol=display,
            ltp=Decimal(str(raw.get("last_price", 0))),
            open=Decimal(str(ohlc.get("open", 0))),
            high=Decimal(str(ohlc.get("high", 0))),
            low=Decimal(str(ohlc.get("low", 0))),
            close=Decimal(str(ohlc.get("close", 0))),
            volume=int(raw.get("volume", 0)),
            change=Decimal(str(raw.get("net_change", 0))),
        )
        logger.debug(
            "quote_fetched", extra={"symbol": symbol, "ltp": str(quote.ltp), "volume": quote.volume}
        )
        return quote

    def get_depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        ref, segment = self._resolve_and_segment(symbol, exchange)
        sid = int(ref.security_id)
        assert_dhan_identity(sid, segment, context="market_data.get_depth")
        data = self._client.post("/marketfeed/quote", json={segment: [sid]})
        raw = data["data"][segment][str(sid)]
        bids = [
            DepthLevel(
                price=Decimal(str(level["price"])),
                quantity=int(level["quantity"]),
                orders=int(level.get("orders", 0)),
            )
            for level in raw.get("depth", {}).get("buy", [])[:5]
        ]
        asks = [
            DepthLevel(
                price=Decimal(str(level["price"])),
                quantity=int(level["quantity"]),
                orders=int(level.get("orders", 0)),
            )
            for level in raw.get("depth", {}).get("sell", [])[:5]
        ]

        display = ref.symbol
        depth = MarketDepth(symbol=display, bids=bids, asks=asks, depth_type="DEPTH_5")
        logger.debug(
            "depth_fetched",
            extra={"symbol": symbol, "bid_levels": len(bids), "ask_levels": len(asks)},
        )
        return depth

    def get_ohlc(self, symbol: str, exchange: str = "NSE") -> dict:
        ref, segment = self._resolve_and_segment(symbol, exchange)
        sid = int(ref.security_id)
        assert_dhan_identity(sid, segment, context="market_data.get_ohlc")
        data = self._client.post("/marketfeed/ohlc", json={segment: [sid]})
        result = data["data"][segment][str(sid)]["ohlc"]
        logger.debug("ohlc_fetched", extra={"symbol": symbol})
        return result

    def get_batch_ltp(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        segment_map: dict[str, list[int]] = {}
        symbol_map: dict[int, str] = {}
        for sym in symbols:
            try:
                ref, segment = self._resolve_and_segment(sym, exchange)
                sid = int(ref.security_id)
                # PR-B: defence-in-depth invariant assertion per-entry.
                assert_dhan_identity(sid, segment, context="market_data.get_batch_ltp")
                segment_map.setdefault(segment, []).append(sid)
                symbol_map[sid] = sym
            except Exception:
                continue
        if not segment_map:
            return {}
        data = self._client.post("/marketfeed/ltp", json=segment_map)
        result = {}
        for _seg, sids in data.get("data", {}).items():
            for sid_str, info in sids.items():
                sid = int(sid_str)
                if sid in symbol_map:
                    result[symbol_map[sid]] = Decimal(str(info.get("last_price", 0)))
        return result

    def get_batch_quote(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        from domain import Quote as DhanQuote

        segment_map: dict[str, list[int]] = {}
        symbol_map: dict[int, str] = {}
        ref_map: dict[int, object] = {}
        for sym in symbols:
            try:
                ref, segment = self._resolve_and_segment(sym, exchange)
                sid = int(ref.security_id)
                # PR-B: defence-in-depth invariant assertion per-entry.
                assert_dhan_identity(sid, segment, context="market_data.get_batch_quote")
                segment_map.setdefault(segment, []).append(sid)
                symbol_map[sid] = sym
                ref_map[sid] = ref
            except Exception:
                continue
        if not segment_map:
            return {}
        data = self._client.post("/marketfeed/quote", json=segment_map)
        result = {}
        for _seg, sids in data.get("data", {}).items():
            for sid_str, info in sids.items():
                sid = int(sid_str)
                if sid in symbol_map:
                    ref = ref_map[sid]
                    ohlc = info.get("ohlc", {}) or {}
                    display = ref.symbol
                    result[symbol_map[sid]] = DhanQuote(
                        symbol=display,
                        ltp=Decimal(str(info.get("last_price", 0))),
                        open=Decimal(str(ohlc.get("open", 0))),
                        high=Decimal(str(ohlc.get("high", 0))),
                        low=Decimal(str(ohlc.get("low", 0))),
                        close=Decimal(str(ohlc.get("close", 0))),
                        volume=int(info.get("volume", 0)),
                        change=Decimal(str(info.get("net_change", 0))),
                    )
        return result

"""Options adapter — option chain, greeks, strike selection, expired data."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Literal

from brokers.dhan.http_client import DhanHttpClient
from brokers.dhan.identity import DhanIdentityProvider, coerce_identity_provider
from brokers.dhan.invariants import assert_dhan_identity

logger = logging.getLogger(__name__)

_DEFAULT_STRIKE_STEPS = {
    "NIFTY": Decimal("50"),
    "BANKNIFTY": Decimal("100"),
    "FINNIFTY": Decimal("50"),
    "MIDCPNIFTY": Decimal("25"),
    "SENSEX": Decimal("100"),
}

# Dhan expired options API requires NSE_FNO segment, not IDX_I
_EXPIRED_EXCHANGE_SEGMENT = "NSE_FNO"


class OptionsAdapter:
    def __init__(self, client: DhanHttpClient, identity: DhanIdentityProvider | object):
        self._client = client
        self._identity = coerce_identity_provider(identity)
        self._resolver = self._identity.resolver

    def get_option_chain(
        self,
        underlying: str,
        exchange: str,
        expiry: str,
        *,
        security_id: int | None = None,
    ) -> dict:
        """Fetch full option chain. Pass security_id for MCX commodities.

        The ``security_id`` parameter is intentionally restricted to the
        MCX path: it is the resolved security_id of a futures contract on
        the same underlying, produced by ``ExtendedCapabilities`` after
        ``self._identity.resolve_ref`` has been called. The MCX option
        chain's ``UnderlyingSeg`` is fixed at ``"MCX_COMM"`` per Dhan.
        """
        if security_id is not None:
            scrip_id = security_id
            segment = "MCX_COMM"
        else:
            ref, segment = self._resolve_and_segment(underlying, exchange)
            scrip_id = int(ref.security_id)

        # PR-B: defence-in-depth invariant assertion. The option-chain
        # endpoint takes a flat ``{UnderlyingScrip, UnderlyingSeg, Expiry}``
        # body, so we verify each (scrip, segment) pair.
        assert_dhan_identity(scrip_id, segment, context="options.get_option_chain")

        response = self._client.post(
            "/optionchain",
            json={
                "UnderlyingScrip": scrip_id,
                "UnderlyingSeg": segment,
                "Expiry": expiry,
            },
        )

        data = response.get("data", response)
        if isinstance(data, dict):
            spot = Decimal(str(data.get("last_price", 0)))
            oc = data.get("oc", {})
        else:
            spot = Decimal("0")
            oc = {}

        strikes = []
        for strike_str, legs in sorted(oc.items(), key=lambda kv: float(kv[0])):
            strike = Decimal(str(strike_str))
            ce = legs.get("ce", {}) or {}
            pe = legs.get("pe", {}) or {}
            ce_greeks = ce.get("greeks", {}) or {}
            pe_greeks = pe.get("greeks", {}) or {}

            ce_sec_id = ce.get("security_id")
            pe_sec_id = pe.get("security_id")

            ce_symbol = ""
            if ce_sec_id:
                try:
                    ce_inst = self._resolver.get_by_security_id(str(ce_sec_id))
                    if ce_inst:
                        ce_symbol = ce_inst.symbol
                except Exception:
                    logger.debug("ce_symbol_resolve_failed: %s", ce_sec_id)

            pe_symbol = ""
            if pe_sec_id:
                try:
                    pe_inst = self._resolver.get_by_security_id(str(pe_sec_id))
                    if pe_inst:
                        pe_symbol = pe_inst.symbol
                except Exception:
                    logger.debug("pe_symbol_resolve_failed: %s", pe_sec_id)

            strikes.append(
                {
                    "strike": strike,
                    "call": {
                        "ltp": _dec(ce.get("last_price")),
                        "oi": int(ce.get("oi", 0) or 0),
                        "volume": int(ce.get("volume", 0) or 0),
                        "iv": _dec(ce.get("implied_volatility")),
                        "delta": _dec(ce_greeks.get("delta")),
                        "theta": _dec(ce_greeks.get("theta")),
                        "gamma": _dec(ce_greeks.get("gamma")),
                        "vega": _dec(ce_greeks.get("vega")),
                        "security_id": ce_sec_id,
                        "symbol": ce_symbol,
                    },
                    "put": {
                        "ltp": _dec(pe.get("last_price")),
                        "oi": int(pe.get("oi", 0) or 0),
                        "volume": int(pe.get("volume", 0) or 0),
                        "iv": _dec(pe.get("implied_volatility")),
                        "delta": _dec(pe_greeks.get("delta")),
                        "theta": _dec(pe_greeks.get("theta")),
                        "gamma": _dec(pe_greeks.get("gamma")),
                        "vega": _dec(pe_greeks.get("vega")),
                        "security_id": pe_sec_id,
                        "symbol": pe_symbol,
                    },
                }
            )

        logger.info(
            "option_chain_fetched",
            extra={
                "underlying": underlying,
                "expiry": expiry,
                "strikes": len(strikes),
                "spot": str(spot),
            },
        )
        return {"underlying": underlying, "expiry": expiry, "spot": spot, "strikes": strikes}

    def get_expiries(self, underlying: str, exchange: str) -> list[str]:
        ref, segment = self._resolve_and_segment(underlying, exchange)
        # PR-B: defence-in-depth invariant assertion.
        assert_dhan_identity(int(ref.security_id), segment, context="options.get_expiries")
        response = self._client.post(
            "/optionchain/expirylist",
            json={
                "UnderlyingScrip": int(ref.security_id),
                "UnderlyingSeg": segment,
            },
        )
        data = response.get("data", {})
        if isinstance(data, dict):
            values = data.get("expiryList") or data.get("expiries") or []
        else:
            values = data if isinstance(data, list) else []
        result = [str(v) for v in values]
        logger.info("expiries_fetched", extra={"underlying": underlying, "count": len(result)})
        return result

    def get_expired_options_data(
        self,
        security_id: int,
        expiry_flag: Literal["WEEK", "MONTH"],
        expiry_code: int,
        strike: str,
        option_type: Literal["CALL", "PUT"],
        from_date: str,
        to_date: str,
        required_data: list[str] | None = None,
        interval: int = 1,
    ) -> dict:
        """Fetch expired options OHLCV data from Dhan rolling option API.

        Parameters
        ----------
        security_id:
            Underlying security ID (e.g., 13 for NIFTY, 25 for BANKNIFTY).
        expiry_flag:
            ``"WEEK"`` for weekly expiries, ``"MONTH"`` for monthly.
        expiry_code:
            Expiry sequence number: 0=nearest, 1=next, 2=third, 3=fourth.
        strike:
            Strike relative to spot: ``"ATM"``, ``"ATM+1"``, ``"ATM-1"``, etc.
            Index options support ATM+10/ATM-10; others up to ATM+3/ATM-3.
        option_type:
            ``"CALL"`` or ``"PUT"``.
        from_date:
            Start date in ``YYYY-MM-DD`` format.
        to_date:
            End date in ``YYYY-MM-DD`` format.
        required_data:
            Fields to fetch. Defaults to OHLCV + OI + spot.
        interval:
            Candle interval in minutes: 1, 5, 15, 25, or 60.

        Returns
        -------
        dict with keys ``"ce"`` and/or ``"pe"`` containing timestamped arrays.
        """
        if required_data is None:
            required_data = ["open", "high", "low", "close", "volume", "oi", "spot"]

        response = self._client.post(
            "/charts/rollingoption",
            json={
                "securityId": security_id,
                "exchangeSegment": _EXPIRED_EXCHANGE_SEGMENT,
                "instrument": "OPTIDX",
                "expiryFlag": expiry_flag,
                "expiryCode": expiry_code,
                "strike": strike,
                "drvOptionType": option_type,
                "requiredData": required_data,
                "fromDate": from_date,
                "toDate": to_date,
                "interval": interval,
            },
        )

        # HTTP client returns {"data": {"ce": {...}, "pe": {...}}} on success
        # or raises DhanError on failure
        data = response.get("data", {})
        inner = data.get("data", data) if isinstance(data, dict) else {}

        result = {"status": "success", "ce": None, "pe": None}
        if isinstance(inner, dict):
            ce = inner.get("ce")
            pe = inner.get("pe")
            result["ce"] = ce if ce and isinstance(ce, dict) and ce.get("timestamp") else None
            result["pe"] = pe if pe and isinstance(pe, dict) and pe.get("timestamp") else None

        ce_count = len(result["ce"]["timestamp"]) if result["ce"] else 0
        pe_count = len(result["pe"]["timestamp"]) if result["pe"] else 0
        logger.info(
            "expired_options_data_fetched",
            extra={
                "security_id": security_id,
                "expiry_flag": expiry_flag,
                "option_type": option_type,
                "ce_count": ce_count,
                "pe_count": pe_count,
            },
        )
        return result

    def _resolve_and_segment(self, symbol: str, exchange: str):
        """Resolve *symbol* on *exchange* via the identity provider.

        Returns ``(ref, segment)`` where ``ref`` is a
        :class:`DhanInstrumentRef` and ``segment`` is its
        Dhan-internal segment code. The provider enforces the
        Dhan-internal contract on every call.
        """
        ref = self._identity.resolve_ref(symbol, exchange)
        return ref, ref.exchange_segment


def _dec(value) -> Decimal | None:
    if value in (None, ""):
        return None
    return Decimal(str(value))

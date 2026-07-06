"""Options adapter — option chain, expiries, expired options data."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Literal

from brokers.ports.http_client_port import HttpClientPort

from brokers.adapters.dhan.identity import DhanInstrumentResolver

logger = logging.getLogger(__name__)


from brokers.domain.entities import OptionChain, OptionLeg, OptionStrike


class DhanOptions:
    """Options trading adapter for Dhan broker.

    Provides option chain data, expiry lists, and expired options historical data.
    """

    def __init__(
        self,
        client: HttpClientPort,
        resolver: DhanInstrumentResolver,
    ) -> None:
        self._client = client
        self._resolver = resolver

    def get_option_chain(
        self,
        underlying: str,
        exchange: str,
        expiry: str,
        *,
        security_id: int | None = None,
    ) -> OptionChain:
        """Fetch full option chain with greeks.

        Parameters
        ----------
        underlying : str
            Underlying symbol (e.g., "NIFTY", "BANKNIFTY").
        exchange : str
            Exchange code (e.g., "NSE", "NFO").
        expiry : str
            Expiry date in YYYY-MM-DD format.
        security_id : int, optional
            Security ID for MCX commodities. If not provided, resolves from symbol.

        Returns
        -------
        OptionChain
            Option chain with strikes, greeks, and spot price.
        """
        if security_id is not None:
            scrip_id: int | str = security_id
            segment = "MCX_COMM"
        else:
            scrip_id, segment = self._resolve_underlying(underlying, exchange)

        response = self._client.post(
            "/optionchain",
            json={
                "UnderlyingScrip": int(scrip_id),
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

        strikes: list[OptionStrike] = []
        for strike_str, legs in sorted(oc.items(), key=lambda kv: float(kv[0])):
            strike = Decimal(str(strike_str))
            ce = legs.get("ce", {}) or {}
            pe = legs.get("pe", {}) or {}
            ce_greeks = ce.get("greeks", {}) or {}
            pe_greeks = pe.get("greeks", {}) or {}

            ce_sec_id = ce.get("security_id")
            pe_sec_id = pe.get("security_id")

            ce_symbol = self._resolve_symbol(ce_sec_id)
            pe_symbol = self._resolve_symbol(pe_sec_id)

            strikes.append(
                OptionStrike(
                    strike=strike,
                    call=OptionLeg(
                        ltp=_dec(ce.get("last_price")),
                        oi=int(ce.get("oi", 0) or 0),
                        volume=int(ce.get("volume", 0) or 0),
                        iv=_dec(ce.get("implied_volatility")),
                        delta=_dec(ce_greeks.get("delta")),
                        theta=_dec(ce_greeks.get("theta")),
                        gamma=_dec(ce_greeks.get("gamma")),
                        vega=_dec(ce_greeks.get("vega")),
                        security_id=ce_sec_id,
                        symbol=ce_symbol,
                    ),
                    put=OptionLeg(
                        ltp=_dec(pe.get("last_price")),
                        oi=int(pe.get("oi", 0) or 0),
                        volume=int(pe.get("volume", 0) or 0),
                        iv=_dec(pe.get("implied_volatility")),
                        delta=_dec(pe_greeks.get("delta")),
                        theta=_dec(pe_greeks.get("theta")),
                        gamma=_dec(pe_greeks.get("gamma")),
                        vega=_dec(pe_greeks.get("vega")),
                        security_id=pe_sec_id,
                        symbol=pe_symbol,
                    ),
                )
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

        return OptionChain(
            underlying=underlying,
            expiry=expiry,
            spot=spot,
            strikes=tuple(strikes),
        )

    def _resolve_underlying(self, underlying: str, exchange: str) -> tuple[str, str]:
        """Resolve underlying to (security_id, exchange_segment) for option chain API.

        Handles indices (NIFTY → IDX_I), equities (RELIANCE → NSE_EQ),
        and commodities (CRUDEOIL → MCX_COMM) correctly.
        """
        # Try direct resolve first
        try:
            ref = self._resolver.resolve(underlying, exchange)
            return ref.security_id, ref.exchange_segment
        except Exception:
            logger.debug("resolve_direct_failed: %s %s", underlying, exchange)

        # For index underlyings: NSE indices live under IDX_I segment
        # Try resolving against INDEX exchange alias
        try:
            ref = self._resolver.resolve(underlying, "INDEX")
            return ref.security_id, ref.exchange_segment
        except Exception:
            logger.debug("resolve_index_failed: %s", underlying)

        # Search broadly
        results = self._resolver.search(underlying.upper(), limit=50)
        for ref in results:
            if ref.symbol.upper() == underlying.upper():
                return ref.security_id, ref.exchange_segment

        # Try to find commodity futures contracts (e.g. CRUDEOIL-20Jul2026-FUT)
        candidates = []
        for ref in results:
            sym = ref.symbol.upper()
            if sym.startswith(underlying.upper() + "-") and "FUT" in ref.instrument_type.upper():
                candidates.append(ref)
        if candidates:
            # Sort candidates by symbol (chronological by symbol name like CRUDEOIL-20Jul2026-FUT)
            # or just take the first one returned
            return candidates[0].security_id, candidates[0].exchange_segment

        from brokers.domain.exceptions import InstrumentNotFoundError

        raise InstrumentNotFoundError(underlying)

    def get_expiries(self, underlying: str, exchange: str) -> list[str]:
        """Fetch list of available expiry dates for an underlying.

        Parameters
        ----------
        underlying : str
            Underlying symbol (e.g., "NIFTY", "BANKNIFTY", "CRUDEOIL").
        exchange : str
            Exchange code (e.g., "NSE", "NFO", "MCX").

        Returns
        -------
        list[str]
            List of expiry dates in YYYY-MM-DD format.
        """
        scrip_id, segment = self._resolve_underlying(underlying, exchange)

        response = self._client.post(
            "/optionchain/expirylist",
            json={
                "UnderlyingScrip": int(scrip_id),
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
    ) -> dict[str, Any]:
        """Fetch expired options OHLCV data from Dhan rolling option API.

        Parameters
        ----------
        security_id : int
            Underlying security ID (e.g., 13 for NIFTY, 25 for BANKNIFTY).
        expiry_flag : Literal["WEEK", "MONTH"]
            "WEEK" for weekly expiries, "MONTH" for monthly.
        expiry_code : int
            Expiry sequence number: 0=nearest, 1=next, 2=third, 3=fourth.
        strike : str
            Strike relative to spot: "ATM", "ATM+1", "ATM-1", etc.
        option_type : Literal["CALL", "PUT"]
            "CALL" or "PUT".
        from_date : str
            Start date in YYYY-MM-DD format.
        to_date : str
            End date in YYYY-MM-DD format.
        required_data : list[str], optional
            Fields to fetch. Defaults to OHLCV + OI + spot.
        interval : int
            Candle interval in minutes: 1, 5, 15, 25, or 60.

        Returns
        -------
        dict
            Dictionary with "ce" and/or "pe" keys containing timestamped arrays.
        """
        if required_data is None:
            required_data = ["open", "high", "low", "close", "volume", "oi", "spot"]

        response = self._client.post(
            "/charts/rollingoption",
            json={
                "securityId": security_id,
                "exchangeSegment": "NSE_FNO",
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

        data = response.get("data", {})
        inner = data.get("data", data) if isinstance(data, dict) else {}

        ce_series = None
        pe_series = None
        if isinstance(inner, dict):
            raw_ce = inner.get("ce")
            raw_pe = inner.get("pe")
            if raw_ce and isinstance(raw_ce, dict) and raw_ce.get("timestamp"):
                ce_series = raw_ce
            if raw_pe and isinstance(raw_pe, dict) and raw_pe.get("timestamp"):
                pe_series = raw_pe

        ce_count = len(ce_series["timestamp"]) if ce_series else 0
        pe_count = len(pe_series["timestamp"]) if pe_series else 0

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

        return {
            "status": "success",
            "ce": ce_series,
            "pe": pe_series,
        }

    def _resolve_symbol(self, security_id: int | str | None) -> str:
        """Resolve symbol from security ID."""
        if not security_id:
            return ""
        try:
            inst = self._resolver.get_by_security_id(str(security_id))
            return inst.symbol if inst else ""
        except Exception:
            logger.debug("symbol_resolve_failed: %s", security_id)
            return ""


def _dec(value: Any) -> Decimal | None:
    """Convert value to Decimal, returning None for empty/None values."""
    if value in (None, ""):
        return None
    return Decimal(str(value))

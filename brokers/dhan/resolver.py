"""O(1) symbol → Instrument resolver backed by dictionaries.

Index symbols (NIFTY, BANKNIFTY, etc.) are resolved via a hardcoded
fallback in :mod:`config.indices` when they are not present in the
instrument cache.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable

from brokers.dhan.domain import Exchange, Instrument, InstrumentType, OptionType
from brokers.dhan.exceptions import InstrumentNotFoundError
from brokers.dhan.segments import SEGMENT_TO_EXCHANGE
from domain.entities.instrument import Instrument as DomainInstrument
from domain.symbols import normalize_exchange, normalize_symbol
from config.indices import get_index_entry, is_index

logger = logging.getLogger(__name__)

_NAME_TO_TYPE: dict[str, InstrumentType] = {
    "EQUITY": InstrumentType.EQUITY,
    "INDEX": InstrumentType.EQUITY,
    "OPTIDX": InstrumentType.OPTION,
    "OPTSTK": InstrumentType.OPTION,
    "OPTCUR": InstrumentType.OPTION,
    "OPTFUT": InstrumentType.OPTION,
    "OPTCOM": InstrumentType.OPTION,
    "FUTIDX": InstrumentType.FUTURE,
    "FUTSTK": InstrumentType.FUTURE,
    "FUTCUR": InstrumentType.FUTURE,
    "FUTCOM": InstrumentType.FUTURE,
}

_DHAN_OPTION_TYPE: dict[str, OptionType] = {
    "CE": OptionType.CALL,
    "CALL": OptionType.CALL,
    "PE": OptionType.PUT,
    "PUT": OptionType.PUT,
}


class SymbolResolver:
    """Thread-safe O(1) symbol → Instrument resolver."""

    def __init__(self) -> None:
        self._by_symbol: dict[tuple[str, Exchange], Instrument] = {}
        self._by_security_id: dict[str, Instrument] = {}
        self._by_underlying: dict[tuple[str, Exchange], list[Instrument]] = {}
        self._loaded = False
        self._lock = threading.RLock()

    def resolve(
        self, symbol: str, exchange: str, *, expected_segment: str | None = None
    ) -> Instrument:
        """Resolve symbol to Instrument.

        Args:
            symbol: Trading symbol
            exchange: Exchange code
            expected_segment: Optional hint to prevent index-vs-derivative misroutes
        """
        exch = self._normalise_exchange(exchange)
        inst = self._find(symbol, exch, expected_segment=expected_segment)
        if inst is None:
            raise InstrumentNotFoundError(
                f"Instrument not found: symbol={symbol!r}, exchange={exchange!r}"
            )
        return inst

    def get_by_symbol(self, symbol: str, exchange: str) -> Instrument | None:
        try:
            return self._find(symbol, self._normalise_exchange(exchange))
        except Exception:
            return None

    def get_by_security_id(self, security_id: str) -> Instrument | None:
        return self._by_security_id.get(str(security_id))

    def get_futures(self, underlying: str, exchange: str) -> list[Instrument]:
        exch = self._normalise_exchange(exchange)
        key = (normalize_symbol(underlying), exch)
        contracts = self._by_underlying.get(key, [])
        return sorted(contracts, key=lambda i: (i.expiry or "9999-12-31"))

    def get_futures_expiries(self, underlying: str, exchange: str) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for c in self.get_futures(underlying, exchange):
            if c.expiry and c.expiry not in seen:
                seen.add(c.expiry)
                result.append(c.expiry)
        return result

    def get_lot_size(self, symbol: str, exchange: str) -> int:
        return self.resolve(symbol, exchange).lot_size

    def stats(self) -> dict:
        return {"loaded": self._loaded, "total": len(self._by_security_id)}

    def all_instruments(self) -> list[Instrument]:
        return list(self._by_security_id.values())

    def load_from_rows(self, rows: Iterable[dict]) -> dict[str, int | float]:
        """Load instruments from CSV rows with atomic swap.

        Returns:
            Dict with keys: total, skipped, skip_rate
        """
        new_by_symbol: dict[tuple[str, Exchange], Instrument] = {}
        new_by_sid: dict[str, Instrument] = {}
        new_by_underlying: dict[tuple[str, Exchange], list[Instrument]] = {}
        skipped = 0

        for row in rows:
            try:
                inst = self._row_to_instrument(row)
            except Exception:
                skipped += 1
                continue

            if inst is None:
                skipped += 1
                continue

            # Generate robust alternate keys
            alt_keys = _generate_alternate_keys(
                symbol=inst.symbol,
                inst_type=inst.instrument_type,
                expiry=inst.expiry,
                strike=inst.strike_price,
                option_type=inst.option_type,
                underlying=inst.underlying,
                canonical_symbol=inst.canonical_symbol,
                sm_symbol_name=inst.sm_symbol_name,
            )

            # Register all alternate keys, preferring EQUITY/FUTURE over OPTION
            # so that "USDINR" on CDS resolves to the continuous future, not
            # an expired currency option.
            for k in alt_keys:
                existing = new_by_symbol.get((k, inst.exchange))
                if existing is None or (existing.is_option and not inst.is_option):
                    new_by_symbol[(k, inst.exchange)] = inst
                elif existing.is_future and inst.is_future:
                    # Prefer the nearest active future (closest expiry >= today)
                    from datetime import date

                    today = str(date.today())
                    e_exp = existing.expiry or ""
                    i_exp = inst.expiry or ""
                    e_active = e_exp >= today
                    i_active = i_exp >= today
                    if (
                        (i_active and not e_active)
                        or (i_active and e_active and i_exp < e_exp)
                        or (not i_active and not e_active and i_exp > e_exp)
                    ):
                        new_by_symbol[(k, inst.exchange)] = inst

            new_by_sid[inst.security_id] = inst

            # Index by underlying for futures
            if inst.is_future and inst.underlying:
                ukey = (inst.underlying.upper(), inst.exchange)
                new_by_underlying.setdefault(ukey, []).append(inst)

        with self._lock:
            self._by_symbol = new_by_symbol
            self._by_security_id = new_by_sid
            self._by_underlying = new_by_underlying
            self._loaded = True

        total_loaded = len(new_by_sid)
        total_processed = total_loaded + skipped
        skip_rate = skipped / total_processed if total_processed > 0 else 0.0

        result = {
            "total": total_loaded,
            "skipped": skipped,
            "skip_rate": skip_rate,
        }

        if skip_rate > 0.01:
            logger.warning(
                "high_skip_rate_in_resolver",
                extra={"skipped": skipped, "total": total_processed, "rate": skip_rate},
            )

        logger.info(
            "instrument cache loaded: total=%d skipped=%d skip_rate=%.2f%%",
            total_loaded,
            skipped,
            skip_rate * 100,
        )

        return result

    # ── internals ──

    def _find(
        self, symbol: str, exch: Exchange, *, expected_segment: str | None = None
    ) -> Instrument | None:
        """Find instrument with progressive lookup.

        Args:
            symbol: Trading symbol
            exch: Exchange enum
            expected_segment: Optional hint to prevent index-vs-derivative misroutes
        """
        clean = normalize_symbol(symbol)

        # 1. Try direct lookup
        inst = self._by_symbol.get((clean, exch))
        if inst is not None:
            return inst

        # 2. Try stripped lookup
        stripped = clean.replace(" ", "").replace("-", "").replace("_", "")
        inst = self._by_symbol.get((stripped, exch))
        if inst is not None:
            return inst

        # 3. Try standardizing Option format CALL -> CE, PUT -> PE
        if clean.endswith("CALL"):
            clean = clean[:-4] + "CE"
        elif clean.endswith("PUT"):
            clean = clean[:-3] + "PE"

        inst = self._by_symbol.get((clean, exch))
        if inst is not None:
            return inst

        # 4. Try stripped Option format standard
        stripped_cepe = clean.replace(" ", "").replace("-", "").replace("_", "")
        inst = self._by_symbol.get((stripped_cepe, exch))
        if inst is not None:
            return inst

        # 5. Index fallback: if symbol is a known index, try Exchange.INDEX
        #    Indices are often stored with exchange=INDEX in the CSV, but
        #    users typically query with exchange=NSE.  This fallback catches
        #    that case when the cache is populated with index instruments.
        if is_index(clean):
            index_exch = Exchange("INDEX")
            if exch != index_exch:
                idx_inst = self._by_symbol.get((clean, index_exch))
                if idx_inst is not None:
                    return idx_inst
                # Also try stripped
                idx_inst = self._by_symbol.get((stripped, index_exch))
                if idx_inst is not None:
                    return idx_inst

        # 6. Hardcoded index fallback: if symbol is a known index with a
        #    hardcoded Dhan security_id, create a synthetic Instrument.
        #    This works even when instruments are NOT loaded (load_instruments=False)
        #    or the index isn't present in the CSV.
        if is_index(clean):
            entry = get_index_entry(clean)
            if entry and entry.dhan_security_id:
                # Guard against index fallback when derivatives expected
                if expected_segment:
                    derivative_segments = {
                        "NSE_FNO",
                        "BSE_FNO",
                        "MCX_COMM",
                        "NSE_CURRENCY",
                        "BSE_CURRENCY",
                    }
                    if expected_segment in derivative_segments:
                        raise InstrumentNotFoundError(
                            f"{symbol} is an index; specify the derivative contract symbol "
                            f"e.g. NIFTY 26 JUN 25000 CE for {expected_segment}"
                        )

                from decimal import Decimal

                logger.info(
                    "index_resolved_via_hardcoded_id",
                    extra={
                        "symbol": clean,
                        "security_id": entry.dhan_security_id,
                        "canonical_name": entry.canonical_name,
                    },
                )
                # Create domain instrument first
                domain_inst = DomainInstrument(
                    symbol=clean,
                    exchange="INDEX",
                    security_id=entry.dhan_security_id,
                    instrument_type="EQUITY",
                    lot_size=1,
                    tick_size=Decimal("0.05"),
                    name="INDEX",
                    canonical_symbol=entry.canonical_name,
                )
                return Instrument(
                    domain_instrument=domain_inst,
                    exchange=Exchange("INDEX"),
                    instrument_type=InstrumentType.EQUITY,
                )

        return None

    @staticmethod
    def _normalise_exchange(exchange: str) -> Exchange:
        up = normalize_exchange(exchange)
        try:
            return Exchange(up)
        except ValueError as e:
            mapped = SEGMENT_TO_EXCHANGE.get(up)
            if mapped is None:
                raise InstrumentNotFoundError(f"Unknown exchange: {exchange!r}") from e
            return Exchange(mapped)

    @staticmethod
    def _row_to_instrument(row: dict) -> Instrument | None:
        symbol = (row.get("SEM_TRADING_SYMBOL") or "").strip()
        security_id = str(row.get("SEM_SMST_SECURITY_ID") or "").strip()
        if not symbol or not security_id:
            return None
        try:
            if int(float(security_id)) <= 0:
                return None
        except (TypeError, ValueError):
            return None

        segment = normalize_exchange(row.get("SEM_EXM_EXCH_ID") or "")
        exch_str = SEGMENT_TO_EXCHANGE.get(segment)
        if exch_str is None:
            return None
        exchange = Exchange(exch_str)

        name = normalize_symbol(row.get("SEM_INSTRUMENT_NAME") or "")
        itype = _NAME_TO_TYPE.get(name)
        if itype is None:
            return None

        lot_size = _safe_int(row.get("SEM_LOT_UNITS"), default=1)
        tick_size = _safe_decimal(row.get("SEM_TICK_SIZE"), default="0.05")

        option_type: OptionType | None = None
        strike_price = None
        expiry = None
        underlying = None
        canonical = (row.get("SEM_CUSTOM_SYMBOL") or "").strip() or None

        # SM_SYMBOL_NAME is the authoritative underlying name from Dhan CSV
        sm_symbol_name = (row.get("SM_SYMBOL_NAME") or "").strip() or None

        if itype in (InstrumentType.OPTION, InstrumentType.FUTURE):
            expiry = row.get("SEM_EXPIRY_DATE")
            if itype == InstrumentType.OPTION:
                opt_raw = normalize_symbol(row.get("SEM_OPTION_TYPE") or "")
                option_type = _DHAN_OPTION_TYPE.get(opt_raw)
                strike_price = (
                    _safe_decimal(row.get("SEM_STRIKE_PRICE"))
                    if row.get("SEM_STRIKE_PRICE") is not None
                    else None
                )

            # Prefer SM_SYMBOL_NAME for underlying (root cause fix)
            if sm_symbol_name:
                underlying = sm_symbol_name.split()[0].upper()
            elif canonical:
                underlying = canonical.split()[0].upper()
            elif "-" in symbol:
                underlying = symbol.split("-", 1)[0].upper()
            else:
                import re

                m = re.match(r"^([A-Z]+)\d+[A-Z]{3}FUT$", symbol.upper())
                underlying = (m.group(1)                if m else symbol).upper()

        # Create domain instrument first
        domain_inst = DomainInstrument(
            symbol=symbol,
            exchange=exchange.value,
            security_id=security_id,
            instrument_type=itype.value,
            lot_size=lot_size,
            tick_size=tick_size,
            name=name,
            option_type=option_type.value if option_type else None,
            strike_price=strike_price,
            expiry=expiry,
            underlying=underlying,
            canonical_symbol=canonical,
        )

        return Instrument(
            domain_instrument=domain_inst,
            exchange=exchange,
            instrument_type=itype,
            option_type=option_type,
            sm_symbol_name=sm_symbol_name,
        )


def _safe_int(value, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_decimal(value, default: str = "0"):
    from decimal import Decimal

    if value is None:
        return Decimal(default)
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _generate_alternate_keys(
    symbol: str,
    inst_type: str | InstrumentType,
    expiry: str | None,
    strike,
    option_type,
    underlying: str | None,
    canonical_symbol: str | None,
    sm_symbol_name: str | None = None,
) -> list[str]:
    keys = []

    # 1. Primary symbol (SEM_TRADING_SYMBOL)
    sym_up = normalize_symbol(symbol)
    keys.append(sym_up)

    # 2. Canonical symbol (SEM_CUSTOM_SYMBOL)
    if canonical_symbol:
        canon_up = normalize_symbol(canonical_symbol)
        keys.append(canon_up)
        # Also generate CE/PE variant when SEM_CUSTOM_SYMBOL has CALL/PUT
        if canon_up.endswith(" CALL"):
            keys.append(canon_up[:-5] + " CE")
        elif canon_up.endswith(" PUT"):
            keys.append(canon_up[:-4] + " PE")

    # 3. Stripped symbol (no spaces, dashes, underscores)
    stripped = sym_up.replace(" ", "").replace("-", "").replace("_", "")
    keys.append(stripped)

    # 4. SM_SYMBOL_NAME as bare lookup key (e.g. "CRUDEOIL", "GOLDM", "USDINR")
    #    This is the root cause fix — enables resolution by underlying name.
    if sm_symbol_name:
        keys.append(normalize_symbol(sm_symbol_name))

    # Standardize option type and instrument type
    type_str = str(inst_type).upper()
    is_option = "OPT" in type_str or "OPTION" in type_str
    is_future = "FUT" in type_str or "FUTURE" in type_str

    if (is_option or is_future) and expiry and underlying:
        try:
            from datetime import datetime

            dt = datetime.strptime(expiry[:10], "%Y-%m-%d")
            dd = dt.strftime("%d")
            dd_strip = str(int(dd))
            mmm = dt.strftime("%b").upper()
            yy = dt.strftime("%y")
            yyyy = dt.strftime("%Y")

            # Month character for weekly options (1-9, O, N, D)
            month_chars = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "O", "N", "D"]
            month_char = month_chars[dt.month - 1]

            und_up = normalize_symbol(underlying)

            if is_option:
                opt_str = str(option_type).upper()
                ce_pe = "CE" if "CALL" in opt_str or "CE" in opt_str or "C" in opt_str else "PE"
                call_put = "CALL" if ce_pe == "CE" else "PUT"

                # Format strike price
                strike_str = ""
                if strike is not None:
                    try:
                        st_val = float(strike)
                        strike_str = str(int(st_val)) if st_val % 1 == 0 else str(st_val)
                    except (ValueError, TypeError):
                        strike_str = str(strike)

                # Generate spaced option forms with CE/PE:
                keys.append(f"{und_up} {dd} {mmm} {yy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd_strip} {mmm} {yy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd} {mmm} {yyyy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd_strip} {mmm} {yyyy} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd} {mmm} {strike_str} {ce_pe}")
                keys.append(f"{und_up} {dd_strip} {mmm} {strike_str} {ce_pe}")

                # Generate spaced option forms with CALL/PUT:
                keys.append(f"{und_up} {dd} {mmm} {strike_str} {call_put}")
                keys.append(f"{und_up} {dd_strip} {mmm} {strike_str} {call_put}")

                # Generate compact option forms:
                keys.append(f"{und_up}{dd}{mmm}{yy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd_strip}{mmm}{yy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd}{mmm}{yyyy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd_strip}{mmm}{yyyy}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd}{mmm}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{dd_strip}{mmm}{strike_str}{ce_pe}")

                # Weekly format: e.g. NIFTY2662525000CE
                keys.append(f"{und_up}{yy}{month_char}{dd}{strike_str}{ce_pe}")
                keys.append(f"{und_up}{yy}{month_char}{dd_strip}{strike_str}{ce_pe}")

            elif is_future:
                keys.append(f"{und_up} {mmm} FUT")
                keys.append(f"{und_up} {yy} {mmm} FUT")
                keys.append(f"{und_up} {yyyy} {mmm} FUT")
                keys.append(f"{und_up} {dd} {mmm} FUT")
                keys.append(f"{und_up} FUT")

                keys.append(f"{und_up}{mmm}FUT")
                keys.append(f"{und_up}{yy}{mmm}FUT")
                keys.append(f"{und_up}{yyyy}{mmm}FUT")
                keys.append(f"{und_up}{dd}{mmm}FUT")
                keys.append(f"{und_up}FUT")
        except Exception as exc:
            logger.debug("alternate_key_generation_failed: %s", exc)

    res = []
    seen = set()
    for k in keys:
        k_clean = normalize_symbol(k)
        if k_clean and k_clean not in seen:
            seen.add(k_clean)
            res.append(k_clean)
    return res

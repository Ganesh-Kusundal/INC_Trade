"""Dhan security ID mapping — translates between canonical and Dhan IDs."""

from __future__ import annotations

from typing import Any, Optional

from tradex.domain.enums import Exchange, InstrumentType
from tradex.domain.mapping import InstrumentMapper, SecurityMapping


class DhanMapper(InstrumentMapper):
    """Dhan-specific security ID mapper."""

    def _parse_row(self, row: dict[str, Any]) -> Optional[SecurityMapping]:
        """Parse a Dhan security master CSV row."""
        exchange_map = {
            "NSE": Exchange.NSE,
            "BSE": Exchange.BSE,
            "MCX": Exchange.MCX,
        }
        instrument_map = {
            "EQUITY": InstrumentType.EQUITY,
            "INDEX": InstrumentType.INDEX,
            "FUTIDX": InstrumentType.FUTIDX,
            "FUTSTK": InstrumentType.FUTSTK,
            "OPTIDX": InstrumentType.OPTIDX,
            "OPTSTK": InstrumentType.OPTSTK,
            "FUTCOM": InstrumentType.FUTCOM,
            "OPTFUT": InstrumentType.OPTFUT,
            "FUTCUR": InstrumentType.FUTCUR,
            "OPTCUR": InstrumentType.OPTCUR,
        }

        exch_str = row.get("SEM_EXM_EXCH_ID", "")
        instr_str = row.get("SEM_INSTRUMENT_NAME", "")

        return SecurityMapping(
            canonical_symbol=row.get("SEM_TRADING_SYMBOL", ""),
            canonical_exchange=exchange_map.get(exch_str, Exchange.UNKNOWN),
            broker_security_id=str(row.get("SEM_SMST_SECURITY_ID", "")),
            broker_symbol=row.get("SEM_TRADING_SYMBOL", ""),
            broker_exchange=exch_str,
            instrument_type=instrument_map.get(instr_str, InstrumentType.UNKNOWN),
            lot_size=int(row.get("SEM_LOT_UNITS", 1)),
            tick_size=float(row.get("SEM_TICK_SIZE", "0.05")),
            isin=row.get("SEM_ISIN", ""),
            extra={
                "custom_symbol": row.get("SEM_CUSTOM_SYMBOL", ""),
                "expiry_date": row.get("SEM_EXPIRY_DATE", ""),
                "strike_price": row.get("SEM_STRIKE_PRICE", ""),
                "option_type": row.get("SEM_OPTION_TYPE", ""),
                "expiry_flag": row.get("SEM_EXPIRY_FLAG", ""),
            },
        )

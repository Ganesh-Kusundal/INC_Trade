"""Canonical exchange identifiers and segment aliases."""

from __future__ import annotations

# Human-friendly exchange codes used in APIs, CLI, and tests.
NSE = "NSE"
BSE = "BSE"
NFO = "NFO"
BFO = "BFO"
MCX = "MCX"
CDS = "CDS"
BCD = "BCD"
IDX = "IDX"

# Wire-format segment strings (broker payloads).
WIRE_NSE_EQ = "NSE_EQ"
WIRE_BSE_EQ = "BSE_EQ"
WIRE_NSE_FNO = "NSE_FNO"
WIRE_BSE_FNO = "BSE_FNO"
WIRE_MCX_COMM = "MCXCOMM"
WIRE_NSE_CURRENCY = "NSE_CURRENCY"
WIRE_BSE_CURRENCY = "BSE_CURRENCY"
WIRE_IDX = "IDX_I"

__all__ = [
    "BCD",
    "BFO",
    "BSE",
    "CDS",
    "IDX",
    "MCX",
    "NFO",
    "NSE",
    "WIRE_BSE_CURRENCY",
    "WIRE_BSE_EQ",
    "WIRE_BSE_FNO",
    "WIRE_IDX",
    "WIRE_MCX_COMM",
    "WIRE_NSE_CURRENCY",
    "WIRE_NSE_EQ",
    "WIRE_NSE_FNO",
]

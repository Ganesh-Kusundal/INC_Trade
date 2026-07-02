"""Centralized error codes for TradeXV2.

All error codes follow the pattern: MODULE_ERR_DESCRIPTION
Used for logging, metrics, and error correlation.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Dhan API Error Codes
# ---------------------------------------------------------------------------

DHAN_ERR_INVALID_TOKEN = "DH-906"
DHAN_ERR_TOKEN_EXPIRED = "DH-808"

# ---------------------------------------------------------------------------
# Broker Error Codes (BRO-xxx)
# ---------------------------------------------------------------------------

BRO_ERR_AUTH_FAILED = "BRO-001"
BRO_ERR_TOKEN_REFRESH_FAILED = "BRO-002"
BRO_ERR_RATE_LIMITED = "BRO-003"
BRO_ERR_CIRCUIT_BREAKER_OPEN = "BRO-004"
BRO_ERR_INSTRUMENT_NOT_FOUND = "BRO-005"
BRO_ERR_ORDER_FAILED = "BRO-006"
BRO_ERR_CONNECTION_FAILED = "BRO-007"
BRO_ERR_TIMEOUT = "BRO-008"
BRO_ERR_NOT_SUPPORTED = "BRO-009"

# ---------------------------------------------------------------------------
# Datalake Error Codes (DLK-xxx)
# ---------------------------------------------------------------------------

DLK_ERR_DATA_NOT_FOUND = "DLK-001"
DLK_ERR_VALIDATION_FAILED = "DLK-002"
DLK_ERR_IO_FAILED = "DLK-003"
DLK_ERR_SCHEMA_MISMATCH = "DLK-004"
DLK_ERR_CONNECTION_FAILED = "DLK-005"

# ---------------------------------------------------------------------------
# Configuration Error Codes (CFG-xxx)
# ---------------------------------------------------------------------------

CFG_ERR_MISSING_REQUIRED = "CFG-001"
CFG_ERR_INVALID_VALUE = "CFG-002"
CFG_ERR_ENV_NOT_SET = "CFG-003"

# ---------------------------------------------------------------------------
# Validation Error Codes (VAL-xxx)
# ---------------------------------------------------------------------------

VAL_ERR_INVALID_SYMBOL = "VAL-001"
VAL_ERR_INVALID_PATH = "VAL-002"
VAL_ERR_PATH_TRAVERSAL = "VAL-003"
VAL_ERR_INVALID_URL = "VAL-004"
VAL_ERR_INJECTION_DETECTED = "VAL-005"

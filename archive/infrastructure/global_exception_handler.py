"""Global exception handler for centralized error-to-response mapping.

Provides consistent HTTP error responses across all API endpoints.
Maps TradeXV2Error hierarchy to appropriate HTTP status codes and
structured error payloads.

Usage in FastAPI:
    from infrastructure.global_exception_handler import setup_exception_handlers

    app = FastAPI()
    setup_exception_handlers(app)
"""

from __future__ import annotations

import logging
import os
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from brokers.common.resilience.errors import (
    AuthenticationError,
    BrokerDegradedError,
    BrokerError,
    CircuitBreakerOpenError,
    InstrumentNotFoundError,
    NonRetryableError,
    NotSupportedError,
    OrderError,
    RateLimitError,
    RetryableError,
)
from domain.exceptions import (
    ConfigError,
    DataError,
    TradeXV2Error,
    ValidationError,
)
from infrastructure.correlation import get_current_correlation_id
from infrastructure.metrics.registry import metrics_registry

logger = logging.getLogger(__name__)

_exceptions_total = metrics_registry.counter("exceptions_total", "Total exceptions by type")
_exceptions_by_status = metrics_registry.counter("exceptions_by_status", "Total exceptions by HTTP status")


class ErrorResponse:
    """Structured error response payload."""

    def __init__(
        self,
        error_type: str,
        message: str,
        status_code: int,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "type": self.error_type,
                "message": self.message,
                "status_code": self.status_code,
                "details": self.details,
            }
        }


def _map_exception_to_response(exc: TradeXV2Error) -> ErrorResponse:
    """Map exception to HTTP response."""

    # Broker errors
    if isinstance(exc, AuthenticationError):
        return ErrorResponse(
            error_type="broker_auth_error",
            message=str(exc),
            status_code=401,
        )

    if isinstance(exc, RateLimitError):
        return ErrorResponse(
            error_type="rate_limit_exceeded",
            message=str(exc),
            status_code=429,
        )

    # Order errors
    if isinstance(exc, OrderError):
        return ErrorResponse(
            error_type="order_execution_error",
            message=str(exc),
            status_code=400,
        )

    # Service-unavailable (503) — circuit breaker / degraded broker
    if isinstance(exc, (CircuitBreakerOpenError, BrokerDegradedError)):
        return ErrorResponse(
            error_type="service_unavailable",
            message=str(exc),
            status_code=503,
        )

    # Not-found (404)
    if isinstance(exc, InstrumentNotFoundError):
        return ErrorResponse(
            error_type="instrument_not_found",
            message=str(exc),
            status_code=404,
        )

    # Validation (422)
    if isinstance(exc, ValidationError):
        return ErrorResponse(
            error_type="validation_error",
            message=str(exc),
            status_code=422,
        )

    # Not-supported (501)
    if isinstance(exc, NotSupportedError):
        return ErrorResponse(
            error_type="not_supported",
            message=str(exc),
            status_code=501,
        )

    # Data / config errors (500)
    if isinstance(exc, DataError):
        return ErrorResponse(
            error_type="data_error",
            message=str(exc),
            status_code=500,
        )

    if isinstance(exc, ConfigError):
        return ErrorResponse(
            error_type="config_error",
            message=str(exc),
            status_code=500,
        )

    # Recoverable (retryable) vs non-retryable
    if isinstance(exc, RetryableError):
        return ErrorResponse(
            error_type="recoverable_error",
            message=str(exc),
            status_code=503,
        )

    if isinstance(exc, NonRetryableError):
        return ErrorResponse(
            error_type="fatal_error",
            message=str(exc),
            status_code=500,
        )

    if isinstance(exc, BrokerError):
        return ErrorResponse(
            error_type="broker_error",
            message=str(exc),
            status_code=502,
        )

    # Default for TradeXV2Error
    return ErrorResponse(
        error_type="tradexv2_error",
        message=str(exc),
        status_code=500,
    )


async def tradexv2_exception_handler(
    request: Request,
    exc: TradeXV2Error,
) -> JSONResponse:
    """Global exception handler for TradeXV2Error."""

    error_response = _map_exception_to_response(exc)

    _exceptions_total.inc()
    _exceptions_by_status.inc()

    logger.error(
        "Exception caught: %s - %s",
        error_response.error_type,
        error_response.message,
        extra={
            "path": request.url.path,
            "method": getattr(request, "method", "WEBSOCKET"),
            "status_code": error_response.status_code,
        },
    )

    content = error_response.to_dict()
    correlation_id = get_current_correlation_id()
    if correlation_id:
        content["correlation_id"] = correlation_id

    return JSONResponse(
        status_code=error_response.status_code,
        content=content,
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Fallback handler for unexpected exceptions."""

    _exceptions_total.inc()
    _exceptions_by_status.inc()

    logger.exception(
        "Unexpected exception: %s",
        str(exc),
        extra={
            "path": request.url.path,
            "method": getattr(request, "method", "WEBSOCKET"),
        },
    )

    details: dict[str, str] = {}
    if os.getenv("TRADEXV2_DEBUG", "").lower() in ("1", "true"):
        details["type"] = type(exc).__name__

    content: dict[str, Any] = {
        "error": {
            "type": "internal_server_error",
            "message": "An unexpected error occurred",
            "status_code": 500,
            "details": details,
        }
    }
    correlation_id = get_current_correlation_id()
    if correlation_id:
        content["correlation_id"] = correlation_id

    return JSONResponse(
        status_code=500,
        content=content,
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers on FastAPI app.

    Args:
        app: FastAPI application instance.
    """
    app.add_exception_handler(
        TradeXV2Error,
        tradexv2_exception_handler,
    )
    app.add_exception_handler(
        Exception,
        generic_exception_handler,
    )


__all__ = [
    "ErrorResponse",
    "setup_exception_handlers",
    "tradexv2_exception_handler",
]

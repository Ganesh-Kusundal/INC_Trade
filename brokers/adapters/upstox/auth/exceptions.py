"""Upstox API exceptions."""

from __future__ import annotations

from typing import Any

from inc_trade.domain.exceptions import BrokerError


class UpstoxApiError(BrokerError):
    """Raised when the Upstox REST API returns a 4xx/5xx or error status."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body

    def __repr__(self) -> str:
        if self.status_code is None:
            return f"UpstoxApiError({self.args[0]!r})"
        return f"UpstoxApiError(message={self.args[0]!r}, status_code={self.status_code!r})"


class UpstoxAuthError(UpstoxApiError):
    """Raised during Upstox OAuth / token lifecycle errors."""

    def __repr__(self) -> str:
        if self.status_code is None:
            return f"UpstoxAuthError({self.args[0]!r})"
        return f"UpstoxAuthError(message={self.args[0]!r}, status_code={self.status_code!r})"

from __future__ import annotations

from typing import Any

from brokers.common.resilience.errors import BrokerError


class UpstoxApiError(BrokerError):
    """Raised when the Upstox REST API returns a 4xx/5xx or error status."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self._message = message
        self.status_code = status_code
        self.body = body

    def __repr__(self) -> str:
        if self.status_code is None:
            return f"UpstoxApiError({self._message!r})"
        return f"UpstoxApiError(message={self._message!r}, status_code={self.status_code!r})"


class UpstoxAuthError(UpstoxApiError):
    """Raised during Upstox OAuth / token lifecycle errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message, status_code=status_code, body=body)

    def __repr__(self) -> str:
        if self.status_code is None:
            return f"UpstoxAuthError({self._message!r})"
        return f"UpstoxAuthError(message={self._message!r}, status_code={self.status_code!r})"

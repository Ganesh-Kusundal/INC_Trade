"""HTTP client port for unified resilient HTTP communication."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class HttpClientPort(Protocol):
    """Protocol for a generic HTTP client with integrated resilience patterns."""

    @property
    def client_id(self) -> str:
        """Client ID used for broker API identification."""
        ...

    def get(self, endpoint: str, params: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """Perform a GET request."""
        ...

    def post(self, endpoint: str, json: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """Perform a POST request."""
        ...

    def put(self, endpoint: str, json: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """Perform a PUT request."""
        ...

    def delete(self, endpoint: str, params: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, Any]:
        """Perform a DELETE request."""
        ...

    def update_token(self, new_token: str) -> None:
        """Update the access token used by the client."""
        ...

    def circuit_breaker_states(self) -> dict[str, int]:
        """Map breaker states to ints: 0=CLOSED, 1=OPEN, 2=HALF_OPEN."""
        ...

    def close(self) -> None:
        """Close the underlying session/connection."""
        ...

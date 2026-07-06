"""Default HTTP client implementing HttpPort."""

from __future__ import annotations

from typing import Any

import requests


class HttpClientImpl:
    """Simple synchronous HTTP client backed by requests."""

    def __init__(self, timeout: float = 10.0) -> None:
        self._timeout = timeout
        self._session = requests.Session()

    async def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        return self._session.request(
            method=method,
            url=url,
            timeout=kwargs.pop("timeout", self._timeout),
            **kwargs,
        )

    async def get(self, url: str, **kwargs: Any) -> requests.Response:
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs: Any) -> requests.Response:
        return await self.request("POST", url, **kwargs)

    async def put(self, url: str, **kwargs: Any) -> requests.Response:
        return await self.request("PUT", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> requests.Response:
        return await self.request("DELETE", url, **kwargs)

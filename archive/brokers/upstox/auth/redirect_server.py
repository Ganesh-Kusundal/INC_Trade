"""Local HTTP server for the OAuth redirect callback.

Mirrors Trade_J ``UpstoxRedirectServer`` — captures the ``?code=`` query
parameter from the OAuth callback and exposes it to the in-process flow.

This module uses ``aiohttp`` (already a project dependency for the Upstox
package) so the existing event loop can host both the redirect server and
the WebSocket multiplexer.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiohttp import web

from .config import UpstoxConnectionSettings
from .exceptions import UpstoxAuthError

logger = logging.getLogger(__name__)

SUCCESS_HTML = (
    b"<html><body><h1>Authorization successful!</h1>"
    b"<p>You can close this window and return to the terminal.</p></body></html>"
)

ERROR_HTML = (
    b"<html><body><h1>Authorization failed</h1>"
    b"<p>Check the error parameter in the URL and try again.</p></body></html>"
)


class UpstoxRedirectServer:
    """Async aiohttp-based local server for the OAuth callback.

    Usage::

        server = UpstoxRedirectServer(settings, path="/cb")
        code = await server.capture_code(timeout=2.0)
        # or as a context manager:
        async with UpstoxRedirectServer(settings) as server:
            code = await server.capture_code(timeout=2.0)
    """

    def __init__(
        self,
        settings: UpstoxConnectionSettings,
        path: str = "/",
        port: int | None = None,
    ) -> None:
        self._settings = settings
        self._path = path
        self._port = port if port is not None else settings.redirect_port
        self._app = web.Application()
        self._app.router.add_get(path, self._handle_callback)
        self._app.router.add_get("/{tail:.*}", self._handle_callback)
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None
        self._code: str | None = None
        self._state: str | None = None
        self._error: str | None = None
        self._received = asyncio.Event()
        self._started = False

    @property
    def redirect_uri(self) -> str:
        return f"http://127.0.0.1:{self._port}{self._path}"

    @property
    def path(self) -> str:
        return self._path

    @property
    def port(self) -> int:
        return self._port

    async def _handle_callback(self, request: web.Request) -> web.Response:
        try:
            code = request.query.get("code")
            state = request.query.get("state")
            error = request.query.get("error")
            if error:
                self._error = error
                self._received.set()
                return web.Response(body=ERROR_HTML, status=400, content_type="text/html")
            if not code:
                self._error = "no code in callback"
                self._received.set()
                return web.Response(body=ERROR_HTML, status=400, content_type="text/html")
            self._code = code
            if state:
                self._state = state
            self._received.set()
            return web.Response(body=SUCCESS_HTML, status=200, content_type="text/html")
        except Exception as exc:
            logger.exception("Error in Upstox redirect server callback")
            self._error = str(exc)
            self._received.set()
            return web.Response(body=ERROR_HTML, status=500, content_type="text/html")

    async def start(self) -> None:
        if self._started:
            return
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, "127.0.0.1", self._port)
        try:
            await self._site.start()
        except OSError as exc:
            raise UpstoxAuthError(
                f"Failed to bind Upstox redirect server to 127.0.0.1:{self._port} ({exc})"
            ) from exc
        if self._port == 0 and self._site is not None:
            server = getattr(self._site, "_server", None)
            sockets = getattr(server, "sockets", None) if server else None
            if sockets:
                with contextlib.suppress(Exception):
                    self._port = sockets[0].getsockname()[1]
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        if self._site is not None:
            with contextlib.suppress(Exception):
                await self._site.stop()
            self._site = None
        if self._runner is not None:
            with contextlib.suppress(Exception):
                await self._runner.cleanup()
            self._runner = None
        self._started = False

    async def capture_code(self, timeout: float = 300.0) -> str:
        if not self._started:
            await self.start()
        try:
            await asyncio.wait_for(self._received.wait(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise asyncio.TimeoutError(f"Authorization timeout after {timeout:.1f}s") from exc
        if self._error:
            raise UpstoxAuthError(f"Authorization error: {self._error}")
        if not self._code:
            raise UpstoxAuthError("No authorization code received")
        return self._code

    async def wait_for_authorization(self, timeout_seconds: float = 300.0) -> str:
        return await self.capture_code(timeout=timeout_seconds)

    @property
    def state(self) -> str | None:
        return self._state

    async def __aenter__(self) -> UpstoxRedirectServer:
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.stop()

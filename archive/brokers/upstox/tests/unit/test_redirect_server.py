"""Tests for UpstoxRedirectServer (aiohttp)."""

from __future__ import annotations

import asyncio

import pytest

aiohttp = pytest.importorskip("aiohttp")
from aiohttp import ClientSession

from brokers.upstox.auth.config import UpstoxConnectionSettings
from brokers.upstox.auth.redirect_server import UpstoxRedirectServer


def _settings(port: int = 0) -> UpstoxConnectionSettings:
    return UpstoxConnectionSettings(
        client_id="cid",
        redirect_uri="http://localhost:18080",
        redirect_port=port,
        environment="LIVE",
    )


def _client_url(server: UpstoxRedirectServer, path: str = "") -> str:
    return server.redirect_uri.replace("127.0.0.1", "localhost") + path


@pytest.mark.asyncio
async def test_captures_code():
    server = UpstoxRedirectServer(_settings(), path="/cb")
    await server.start()
    try:

        async def _hit():
            await asyncio.sleep(0.05)
            async with (
                ClientSession() as session,
                session.get(f"{_client_url(server, '/cb')}?code=hello") as resp,
            ):
                assert resp.status == 200

        asyncio.create_task(_hit())
        code = await server.capture_code(timeout=2.0)
        assert code == "hello"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_default_path():
    server = UpstoxRedirectServer(_settings(), path="/")
    await server.start()
    try:

        async def _hit():
            await asyncio.sleep(0.05)
            async with (
                ClientSession() as session,
                session.get(f"{_client_url(server)}?code=root-code") as resp,
            ):
                assert resp.status == 200

        asyncio.create_task(_hit())
        code = await server.capture_code(timeout=2.0)
        assert code == "root-code"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_timeout_raises():
    server = UpstoxRedirectServer(_settings())
    await server.start()
    try:
        with pytest.raises(TimeoutError):
            await server.capture_code(timeout=0.2)
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_context_manager():
    async with UpstoxRedirectServer(_settings(), path="/cb") as server:

        async def _hit():
            await asyncio.sleep(0.05)
            async with (
                ClientSession() as session,
                session.get(f"{_client_url(server, '/cb')}?code=ctx-code") as resp,
            ):
                assert resp.status == 200

        asyncio.create_task(_hit())
        code = await server.capture_code(timeout=2.0)
        assert code == "ctx-code"


@pytest.mark.asyncio
async def test_duplicate_callback_only_resolves_first():
    server = UpstoxRedirectServer(_settings(), path="/cb")
    await server.start()
    try:

        async def _hit1():
            await asyncio.sleep(0.05)
            async with (
                ClientSession() as session,
                session.get(f"{_client_url(server, '/cb')}?code=first") as resp,
            ):
                assert resp.status == 200

        async def _hit2():
            await asyncio.sleep(0.2)
            async with (
                ClientSession() as session,
                session.get(f"{_client_url(server, '/cb')}?code=second") as resp,
            ):
                assert resp.status == 200

        asyncio.create_task(_hit1())
        asyncio.create_task(_hit2())
        code = await server.capture_code(timeout=2.0)
        assert code == "first"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_redirect_uri_property():
    server = UpstoxRedirectServer(_settings(18080))
    assert server.redirect_uri == "http://127.0.0.1:18080/"


@pytest.mark.asyncio
async def test_capture_starts_server_if_not_started():
    server = UpstoxRedirectServer(_settings(), path="/cb")

    async def _hit():
        await asyncio.sleep(0.1)
        async with (
            ClientSession() as session,
            session.get(f"{_client_url(server, '/cb')}?code=auto") as resp,
        ):
            assert resp.status == 200

    asyncio.create_task(_hit())
    code = await server.capture_code(timeout=2.0)
    assert code == "auto"
    await server.stop()

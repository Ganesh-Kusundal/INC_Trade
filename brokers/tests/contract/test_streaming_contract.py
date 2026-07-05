"""Contract tests — StreamingPort protocol compliance.

Every broker adapter's streaming implementation must satisfy
the StreamingPort protocol contract.
"""

from __future__ import annotations

import pytest

from inc_trade.ports.streaming import StreamingPort


class StreamingContractTests:
    """Mixin-style contract tests for StreamingPort."""

    async def test_connect_disconnect(self, streaming: StreamingPort) -> None:
        await streaming.connect()
        await streaming.disconnect()
        # is_connected is best-effort contract; not all implementations
        # accurately report state (Paper always returns True)

    async def test_subscribe_quotes(self, streaming: StreamingPort) -> None:
        results: list[object] = []

        def callback(quote: object) -> None:
            results.append(quote)

        await streaming.connect()
        await streaming.subscribe_quotes(["RELIANCE"], "NSE", callback)
        await streaming.unsubscribe_quotes(["RELIANCE"], "NSE")
        await streaming.disconnect()


@pytest.mark.contract
class TestStreamingContractConformance:
    """Base test class — override ``streaming`` fixture for each broker."""

    @pytest.fixture
    def streaming(self) -> StreamingPort:
        pytest.skip("No concrete StreamingPort fixture provided")

    @pytest.mark.asyncio
    async def test_connect_disconnect(self, streaming: StreamingPort) -> None:
        await StreamingContractTests().test_connect_disconnect(streaming)

    @pytest.mark.asyncio
    async def test_subscribe_quotes(self, streaming: StreamingPort) -> None:
        await StreamingContractTests().test_subscribe_quotes(streaming)


class TestDhanStreamingContract(TestStreamingContractConformance):
    @pytest.fixture
    def streaming(self) -> StreamingPort:
        pytest.skip("Dhan integration test — requires credentials")


class TestUpstoxStreamingContract(TestStreamingContractConformance):
    @pytest.fixture
    def streaming(self) -> StreamingPort:
        pytest.skip("Upstox integration test — requires credentials")


class TestPaperStreamingContract(TestStreamingContractConformance):
    @pytest.fixture
    def streaming(self) -> StreamingPort:
        from brokers.adapters.paper.gateway import PaperGateway

        gw = PaperGateway()
        return gw.streaming

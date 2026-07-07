"""Integration recovery test — connect / subscribe / disconnect / reconnect.

Uses the in-memory :class:`PaperProvider` (no credentials, no network).
Verifies the provider survives a disconnect/reconnect cycle and that
subscriptions can be re-established without error or deadlock — i.e. that
session state recovers cleanly.
"""

from __future__ import annotations

import pytest

from brokers.domain.enums import Exchange
from brokers.domain.instrument import Instrument
from brokers.domain.values import Quote, Subscription
from brokers.paper.paper_provider import PaperProvider


class TestPaperRecovery:
    """Recovery workflow against the Paper provider."""

    def _reliance(self, provider: PaperProvider) -> Instrument:
        return Instrument(symbol="RELIANCE", exchange=Exchange.NSE, provider=provider)

    @pytest.mark.asyncio
    async def test_connect_subscribe_disconnect_reconnect(self) -> None:
        provider = PaperProvider()
        inst = self._reliance(provider)

        # 1. Connect
        await provider.connect()
        assert provider.is_connected is True

        # 2. Subscribe
        first = await provider.subscribe_quotes([inst])
        assert isinstance(first, Subscription)
        assert first.is_active

        # 3. Disconnect
        await provider.disconnect()
        assert provider.is_connected is False

        # 4. Reconnect
        await provider.connect()
        assert provider.is_connected is True

        # 5. Re-establish subscriptions after recovery
        second = await provider.subscribe_quotes([inst])
        assert isinstance(second, Subscription)
        assert second.is_active

        # 6. Market data still flows after recovery
        quote = await provider.get_quote(inst)
        assert isinstance(quote, Quote)
        assert quote.ltp > 0

        # Cleanup
        await provider.unsubscribe(second)
        await provider.disconnect()
        assert provider.is_connected is False

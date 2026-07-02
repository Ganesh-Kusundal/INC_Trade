"""Live broker infrastructure tests — require TRADEX_LIVE_TESTS=1 and credentials."""

import os
from datetime import date, timedelta

import pytest

from brokers.common.bootstrap import bootstrap_from_broker_registry
from brokers.common.historical_coordinator import HistoricalQuery
from brokers.common.policy import auto_dual_broker_policy
from domain.historical import InstrumentRef

pytestmark = pytest.mark.skipif(
    os.environ.get("TRADEX_LIVE_TESTS") != "1",
    reason="Set TRADEX_LIVE_TESTS=1 and configure broker credentials",
)


@pytest.fixture
async def live_infrastructure():
    brokers = []
    for name in ("dhan", "upstox"):
        try:
            from brokers.common.auth.credential_validator import CredentialValidator

            if CredentialValidator.broker_available(name):
                brokers.append(name)
        except Exception:
            pass
    if not brokers:
        pytest.skip("No live broker credentials available")

    infra = await bootstrap_from_broker_registry(
        brokers,
        policy=auto_dual_broker_policy(),
        load_instruments=False,
        require_authenticated=True,
    )
    if infra is None:
        pytest.skip("Could not bootstrap live broker infrastructure")
    yield infra
    await infra.streams.stop()


class TestLiveBrokerInfrastructure:
    @pytest.mark.asyncio
    async def test_registry_has_live_brokers(self, live_infrastructure):
        assert len(live_infrastructure.registry.list_brokers()) >= 1

    @pytest.mark.asyncio
    async def test_live_quote_snapshot(self, live_infrastructure):
        from brokers.common.models import OperationKind, RoutingRequest
        from brokers.common.quota_scheduler import PriorityClass

        decision = live_infrastructure.router.route(
            RoutingRequest(
                operation=OperationKind.GET_QUOTE,
                trace_id="live-quote-1",
                instrument="RELIANCE:NSE",
            )
        )
        gw = live_infrastructure.registry.get_gateway(decision.primary_broker)
        token = live_infrastructure.quota.acquire(
            decision.primary_broker, "quotes", PriorityClass.PORTFOLIO_READ
        )
        quote = await gw.get_quote_snapshot(InstrumentRef("RELIANCE", "NSE"), quota=token)
        assert quote.ltp > 0

    @pytest.mark.asyncio
    async def test_live_historical_coordinator(self, live_infrastructure):
        today = date.today()
        query = HistoricalQuery(
            instrument=InstrumentRef("RELIANCE", "NSE"),
            timeframe="1D",
            from_date=today - timedelta(days=5),
            to_date=today,
            request_id="live-hist-1",
        )
        series, ledger = await live_infrastructure.historical.fetch(query)
        assert ledger.request_id == "live-hist-1"
        assert series.bar_count >= 0

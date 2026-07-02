"""End-to-end infrastructure bootstrap tests."""

from datetime import date, timedelta

import pytest

from brokers.common.bootstrap import bootstrap_from_gateways, policy_from_env
from brokers.common.historical_coordinator import HistoricalQuery
from brokers.common.policy import RoutingPolicy, SourceSelectionPolicy
from brokers.paper import PaperGateway
from domain.historical import InstrumentRef


def _paper_only_policy() -> SourceSelectionPolicy:
    fixed = RoutingPolicy(mode="fixed", candidates=("paper",), allow_fallback=False)
    return SourceSelectionPolicy(
        historical=fixed,
        live_market_data=fixed,
        execution=RoutingPolicy(
            mode="fixed",
            candidates=("paper",),
            allow_fallback=False,
            execution_account="paper",
        ),
        enrichment=fixed,
        instrument_metadata=fixed,
    )


@pytest.fixture
async def paper_infrastructure():
    infra = await bootstrap_from_gateways(
        [("paper", PaperGateway())],
        policy=_paper_only_policy(),
    )
    yield infra
    await infra.streams.stop()


class TestInfrastructureBootstrap:
    @pytest.mark.asyncio
    async def test_build_infrastructure_registers_paper(self, paper_infrastructure):
        assert "paper" in paper_infrastructure.registry.list_brokers()

    @pytest.mark.asyncio
    async def test_router_selects_paper_for_execution(self, paper_infrastructure):
        from brokers.common.models import OperationKind, RoutingRequest

        decision = paper_infrastructure.router.route(
            RoutingRequest(
                operation=OperationKind.PLACE_ORDER,
                trace_id="e2e-1",
            )
        )
        assert decision.primary_broker == "paper"

    @pytest.mark.asyncio
    async def test_historical_coordinator_fetch(self, paper_infrastructure):
        today = date.today()
        query = HistoricalQuery(
            instrument=InstrumentRef("RELIANCE", "NSE"),
            timeframe="1D",
            from_date=today - timedelta(days=5),
            to_date=today,
            request_id="e2e-hist-1",
        )
        series, ledger = await paper_infrastructure.historical.fetch(query)
        assert series.instrument.symbol == "RELIANCE"
        assert ledger.request_id == "e2e-hist-1"

    @pytest.mark.asyncio
    async def test_quota_scheduler_registered(self, paper_infrastructure):
        metrics = paper_infrastructure.quota.metrics_snapshot()
        assert isinstance(metrics, list)

    def test_policy_from_env_defaults_auto(self):
        policy = policy_from_env()
        assert policy.policy_version

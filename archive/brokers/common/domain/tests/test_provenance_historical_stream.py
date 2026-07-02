"""Integration tests for provenance, historical, and stream health domain models."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from domain.historical import (
    DateRange,
    Gap,
    HistoricalBar,
    HistoricalSeries,
    InstrumentRef,
    MergeManifest,
)
from domain.provenance import DataProvenance, ProvenanceConfidence, SourceIdentity
from domain.stream_health import (
    FreshnessState,
    StreamHealth,
    StreamSession,
    SubscriptionState,
    TransportState,
)


class TestDataProvenance:
    def test_now_stamps_utc_fetched_at(self):
        p = DataProvenance.now(broker_id="dhan", request_id="req-1")
        assert p.source.broker_id == "dhan"
        assert p.fetched_at.tzinfo is not None
        assert p.confidence == ProvenanceConfidence.AUTHORITATIVE

    def test_with_transformation_appends_step(self):
        p = DataProvenance.now(broker_id="dhan", request_id="req-1")
        p2 = p.with_transformation("normalize.ohlcv.v1")
        assert p2.transformation_chain == ("normalize.ohlcv.v1",)

    def test_as_fallback_downgrades_confidence(self):
        p = DataProvenance.now(broker_id="upstox", request_id="req-2")
        fb = p.as_fallback()
        assert fb.confidence == ProvenanceConfidence.FALLBACK

    def test_source_identity_str(self):
        sid = SourceIdentity(broker_id="dhan", account_id="ACC1", connection_id="ws-1")
        assert str(sid) == "dhan:ACC1:ws-1"


class TestHistoricalModels:
    def test_historical_bar_is_frozen(self):
        bar = HistoricalBar(
            instrument=InstrumentRef("RELIANCE", "NSE"),
            timeframe="1D",
            event_time=datetime(2025, 1, 2, 9, 15, tzinfo=timezone.utc),
            open=Decimal("100"),
            high=Decimal("101"),
            low=Decimal("99"),
            close=Decimal("100.5"),
            volume=1000,
            provenance=DataProvenance.now("dhan", "req-1"),
        )
        with pytest.raises(FrozenInstanceError):
            bar.close = Decimal("200")

    def test_historical_series_brokers_contributing(self):
        p = DataProvenance.now("dhan", "req-1")
        bars = [
            HistoricalBar(
                instrument=InstrumentRef("RELIANCE", "NSE"),
                timeframe="1D",
                event_time=datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc),
                open=Decimal("1"),
                high=Decimal("1"),
                low=Decimal("1"),
                close=Decimal("1"),
                volume=1,
                provenance=p,
            ),
            HistoricalBar(
                instrument=InstrumentRef("RELIANCE", "NSE"),
                timeframe="1D",
                event_time=datetime(2025, 1, 2, 9, 15, tzinfo=timezone.utc),
                open=Decimal("2"),
                high=Decimal("2"),
                low=Decimal("2"),
                close=Decimal("2"),
                volume=1,
                provenance=DataProvenance.now("upstox", "req-2"),
            ),
        ]
        series = HistoricalSeries(
            bars=bars,
            coverage=DateRange(date(2025, 1, 1), date(2025, 1, 2)),
            instrument=InstrumentRef("RELIANCE", "NSE"),
            timeframe="1D",
        )
        assert series.brokers_contributing() == {"dhan", "upstox"}

    def test_degraded_series_when_manifest_degraded(self):
        series = HistoricalSeries(
            bars=[],
            coverage=DateRange(date(2025, 1, 1), date(2025, 1, 2)),
            instrument=InstrumentRef("RELIANCE", "NSE"),
            timeframe="1D",
            gaps=[Gap(date(2025, 1, 1), date(2025, 1, 2), "all_failed")],
            merge_manifest=MergeManifest(degraded=True, degraded_reason="all chunks failed"),
        )
        assert series.is_degraded
        assert not series.is_complete


class TestStreamHealth:
    def test_healthy_requires_all_three_dimensions(self):
        health = StreamHealth()
        assert not health.healthy()
        assert "transport" in health.failure_reasons()[0]

        health.transport = TransportState.CONNECTED
        health.subscription = SubscriptionState.ACKNOWLEDGED
        health.freshness = FreshnessState.FRESH
        assert health.healthy()
        assert health.failure_reasons() == []

    def test_stream_session_increments_reconnect(self):
        session = StreamSession(
            session_id="s1",
            broker_id="dhan",
            stream_kind="market",
            instruments=frozenset({"RELIANCE:NSE"}),
            modes=frozenset({"LTP"}),
        )
        assert session.reconnect_generation == 0
        session.increment_reconnect()
        assert session.reconnect_generation == 1

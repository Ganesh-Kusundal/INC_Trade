"""Integration tests for ProvenanceLedger."""

from datetime import date, datetime, timezone

from brokers.common.provenance import BarRangeRecord, ChunkRecord, ConflictRecord, ProvenanceLedger


class TestProvenanceLedger:
    def test_add_chunk_and_summary(self):
        ledger = ProvenanceLedger(
            request_id="req-1",
            instrument="RELIANCE:NSE",
            timeframe="1D",
        )
        ledger.add_chunk(
            ChunkRecord(
                chunk_id="c1",
                broker_id="dhan",
                from_date=date(2025, 1, 1),
                to_date=date(2025, 1, 31),
                timeframe="1D",
                bars_fetched=20,
            )
        )
        ledger.add_chunk(
            ChunkRecord(
                chunk_id="c2",
                broker_id="upstox",
                from_date=date(2025, 2, 1),
                to_date=date(2025, 2, 28),
                timeframe="1D",
                bars_fetched=0,
                error="timeout",
            )
        )
        assert ledger.brokers_used() == {"dhan"}
        assert len(ledger.failed_chunks()) == 1
        assert ledger.total_bars() == 20

        summary = ledger.to_summary_dict()
        assert summary["chunks_failed"] == 1
        assert summary["total_bars"] == 20

    def test_mark_degraded(self):
        ledger = ProvenanceLedger(
            request_id="req-2",
            instrument="RELIANCE:NSE",
            timeframe="1m",
        )
        ledger.mark_degraded("upstox chunk timeout")
        assert ledger.degraded
        assert "timeout" in ledger.degraded_reason

    def test_bar_range_and_conflict_records(self):
        ledger = ProvenanceLedger(
            request_id="req-3",
            instrument="RELIANCE:NSE",
            timeframe="1D",
        )
        ledger.add_bar_range(
            BarRangeRecord(
                start_bar_index=0,
                end_bar_index=9,
                chunk_id="c1",
                broker_id="dhan",
            )
        )
        ledger.add_conflict(
            ConflictRecord(
                bar_event_time=datetime(2025, 1, 15, 9, 15, tzinfo=timezone.utc),
                instrument="RELIANCE:NSE",
                timeframe="1D",
                primary_broker="dhan",
                secondary_broker="upstox",
                primary_close=100,
                secondary_close=105,
                delta_pct=0.05,
                resolution="prefer_primary",
            )
        )
        assert len(ledger.bar_ranges) == 1
        assert len(ledger.conflicts) == 1

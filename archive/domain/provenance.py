"""Provenance model — source identity and data lineage for all broker artifacts.

Every normalized output (bars, ticks, quotes, orders) carries a ``DataProvenance``
so the rest of the system can answer: where did this data come from, what
transformations were applied, and how confident should we be in it?
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ProvenanceConfidence(str, Enum):
    """Confidence level of a normalized artifact's lineage.

    AUTHORITATIVE  — raw data from the primary source, no transformation beyond
                     schema normalization.
    DERIVED        — computed from authoritative data (e.g. resampled bars).
    MERGED         — produced by combining outputs from multiple brokers; all
                     contributing chunks are documented in the provenance.
    FALLBACK       — data from a secondary/fallback source because the primary
                     was unavailable or incomplete.
    """

    AUTHORITATIVE = "AUTHORITATIVE"
    DERIVED = "DERIVED"
    MERGED = "MERGED"
    FALLBACK = "FALLBACK"


@dataclass(frozen=True, slots=True)
class TimestampSemantics:
    """Describes the temporal semantics of a market data artifact.

    event_time      — when the market event occurred (bar open/close, tick time).
    ingest_time     — when the platform received the data from the broker.
    effective_time  — bar label convention (left-labeled vs right-labeled);
                      required on HistoricalBar to disambiguate timestamp meaning.
    """

    event_time: datetime
    ingest_time: datetime
    effective_time: datetime


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    """Identifies the broker source of a normalized artifact.

    broker_id    — canonical broker identifier, e.g. ``"dhan"`` or ``"upstox"``.
    account_id   — execution account identifier when relevant (order results, positions).
    connection_id — stream session or HTTP request identifier for correlation.
    """

    broker_id: str
    account_id: str | None = None
    connection_id: str | None = None

    def __str__(self) -> str:
        parts = [self.broker_id]
        if self.account_id:
            parts.append(self.account_id)
        if self.connection_id:
            parts.append(self.connection_id)
        return ":".join(parts)


@dataclass(frozen=True, slots=True)
class DataProvenance:
    """Full lineage record attached to every normalized domain artifact.

    source              — which broker produced this data.
    fetched_at          — UTC datetime when the platform received the raw data.
    provider_timestamp  — broker-reported event or bar time (None if not provided).
    transformation_chain — ordered list of transformation step identifiers applied
                           before this artifact was emitted, e.g.
                           ``("dhan.intraday.v1", "normalize.ohlcv.v1")``.
    request_id          — ties this artifact back to the routing/quota audit log.
    confidence          — how much to trust the lineage claim.
    """

    source: SourceIdentity
    fetched_at: datetime
    request_id: str
    confidence: ProvenanceConfidence = ProvenanceConfidence.AUTHORITATIVE
    provider_timestamp: datetime | None = None
    transformation_chain: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def now(
        cls,
        broker_id: str,
        request_id: str,
        *,
        confidence: ProvenanceConfidence = ProvenanceConfidence.AUTHORITATIVE,
        account_id: str | None = None,
        connection_id: str | None = None,
        provider_timestamp: datetime | None = None,
        transformation_chain: tuple[str, ...] = (),
    ) -> DataProvenance:
        """Convenience constructor — stamps ``fetched_at`` to UTC now."""
        return cls(
            source=SourceIdentity(
                broker_id=broker_id,
                account_id=account_id,
                connection_id=connection_id,
            ),
            fetched_at=datetime.now(tz=timezone.utc),
            request_id=request_id,
            confidence=confidence,
            provider_timestamp=provider_timestamp,
            transformation_chain=transformation_chain,
        )

    def with_transformation(self, step: str) -> DataProvenance:
        """Return a new provenance with ``step`` appended to the chain."""
        return DataProvenance(
            source=self.source,
            fetched_at=self.fetched_at,
            request_id=self.request_id,
            confidence=self.confidence,
            provider_timestamp=self.provider_timestamp,
            transformation_chain=(*self.transformation_chain, step),
        )

    def as_merged(self) -> DataProvenance:
        """Return a copy with confidence downgraded to MERGED."""
        return DataProvenance(
            source=self.source,
            fetched_at=self.fetched_at,
            request_id=self.request_id,
            confidence=ProvenanceConfidence.MERGED,
            provider_timestamp=self.provider_timestamp,
            transformation_chain=self.transformation_chain,
        )

    def as_fallback(self) -> DataProvenance:
        """Return a copy with confidence downgraded to FALLBACK."""
        return DataProvenance(
            source=self.source,
            fetched_at=self.fetched_at,
            request_id=self.request_id,
            confidence=ProvenanceConfidence.FALLBACK,
            provider_timestamp=self.provider_timestamp,
            transformation_chain=self.transformation_chain,
        )

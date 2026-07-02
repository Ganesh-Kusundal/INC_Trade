"""FeatureSet — domain type for computed features passed to strategy evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FeatureSet:
    """Computed features for strategy evaluation.

    Columnar data container that avoids pandas dependency in the domain layer.
    Adapters convert between FeatureSet and DataFrame at layer boundaries.

    Attributes
    ----------
    columns : mapping of column name → list of values (column-major storage).
    index : optional row index (e.g. dates), aligned with column lengths.
    """

    columns: dict[str, list] = field(default_factory=dict)
    index: list = field(default_factory=list)

    @classmethod
    def empty(cls) -> FeatureSet:
        return cls(columns={}, index=[])

    @property
    def row_count(self) -> int:
        if not self.columns:
            return 0
        return max((len(v) for v in self.columns.values()), default=0)

    @property
    def column_names(self) -> list[str]:
        return list(self.columns.keys())

    @property
    def is_empty(self) -> bool:
        return not self.columns or self.row_count == 0

    def tail(self, n: int) -> FeatureSet:
        """Return the last *n* rows as a new FeatureSet."""
        return FeatureSet(
            columns={k: v[-n:] for k, v in self.columns.items()},
            index=self.index[-n:] if self.index else [],
        )

    def __getitem__(self, col: str) -> list:
        return self.columns[col]

    def __contains__(self, col: str) -> bool:
        return col in self.columns


__all__ = ["FeatureSet"]

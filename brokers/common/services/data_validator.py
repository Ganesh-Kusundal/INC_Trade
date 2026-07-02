"""Data Quality Validation Engine — checks for missing candles, duplicates, OI/volume anomalies, timestamp issues.

Usage:
    from brokers.common.services.data_validator import DataQualityValidator, ValidationReport

    validator = DataQualityValidator()
    report = validator.validate(df, symbol="NIFTY")

    # Individual checks
    missing = validator.check_missing_candles(df, timeframe="1d")
    duplicates = validator.check_duplicates(df)
    oi_anomalies = validator.check_oi_anomalies(df, z_threshold=3.0)
    volume_anomalies = validator.check_volume_anomalies(df, z_threshold=3.0)
    timestamp_issues = validator.check_timestamps(df)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Expected trading hours (IST) for NSE
NSE_OPEN_HOUR = 9
NSE_OPEN_MINUTE = 15
NSE_CLOSE_HOUR = 15
NSE_CLOSE_MINUTE = 30

TIMEFRAME_DELTAS = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
}


@dataclass
class Issue:
    """A single data quality issue."""

    category: str  # missing, duplicate, oi, volume, timestamp
    severity: str  # critical, warning, info
    message: str
    row_index: Any = None
    column: str = ""


@dataclass
class ValidationReport:
    """Complete data quality validation report."""

    symbol: str = ""
    total_rows: int = 0
    total_issues: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    issues: list[Issue] = field(default_factory=list)
    passed: bool = True

    def add(self, issue: Issue) -> None:
        self.issues.append(issue)
        self.total_issues += 1
        if issue.severity == "critical":
            self.critical_count += 1
            self.passed = False
        elif issue.severity == "warning":
            self.warning_count += 1
        else:
            self.info_count += 1

    def summary(self) -> str:
        status = "PASSED" if self.passed else "FAILED"
        lines = [
            f"=== Data Quality Report: {self.symbol} ===",
            f"Status: {status}",
            f"Total rows: {self.total_rows}",
            f"Total issues: {self.total_issues} (critical={self.critical_count}, warning={self.warning_count}, info={self.info_count})",
        ]
        if self.issues:
            lines.append("\nIssues:")
            for i, issue in enumerate(self.issues[:50], 1):  # limit to 50
                lines.append(f"  {i}. [{issue.severity.upper()}] {issue.category}: {issue.message}")
            if len(self.issues) > 50:
                lines.append(f"  ... and {len(self.issues) - 50} more issues")
        return "\n".join(lines)


class DataQualityValidator:
    """Validates OHLCV + OI data for quality issues."""

    def validate(
        self,
        df: pd.DataFrame,
        symbol: str = "",
        timeframe: str = "1d",
        check_missing: bool = True,
        check_duplicates: bool = True,
        check_oi: bool = True,
        check_volume: bool = True,
        check_timestamps: bool = True,
        z_threshold: float = 3.0,
    ) -> ValidationReport:
        """Run all enabled checks and return a report."""
        report = ValidationReport(symbol=symbol, total_rows=len(df))

        if len(df) == 0:
            report.add(Issue("structure", "critical", "Empty DataFrame"))
            return report

        if check_missing:
            self._check_missing_candles(df, timeframe, report)
        if check_duplicates:
            self._check_duplicates(df, report)
        if check_oi and "oi" in df.columns:
            self._check_oi_anomalies(df, z_threshold, report)
        if check_volume and "volume" in df.columns:
            self._check_volume_anomalies(df, z_threshold, report)
        if check_timestamps and "timestamp" in df.columns:
            self._check_timestamps(df, timeframe, report)

        return report

    def check_missing_candles(self, df: pd.DataFrame, timeframe: str = "1d") -> list[Issue]:
        """Check for missing candles based on expected timeframe."""
        report = ValidationReport()
        self._check_missing_candles(df, timeframe, report)
        return report.issues

    def check_duplicates(self, df: pd.DataFrame) -> list[Issue]:
        """Check for duplicate rows."""
        report = ValidationReport()
        self._check_duplicates(df, report)
        return report.issues

    def check_oi_anomalies(self, df: pd.DataFrame, z_threshold: float = 3.0) -> list[Issue]:
        """Check for open interest anomalies using z-score."""
        report = ValidationReport()
        self._check_oi_anomalies(df, z_threshold, report)
        return report.issues

    def check_volume_anomalies(self, df: pd.DataFrame, z_threshold: float = 3.0) -> list[Issue]:
        """Check for volume anomalies using z-score."""
        report = ValidationReport()
        self._check_volume_anomalies(df, z_threshold, report)
        return report.issues

    def check_timestamps(self, df: pd.DataFrame, timeframe: str = "1d") -> list[Issue]:
        """Check for timestamp issues (out of order, missing, non-trading hours)."""
        report = ValidationReport()
        self._check_timestamps(df, timeframe, report)
        return report.issues

    # ── Internal checks ──────────────────────────────────────────────

    def _check_missing_candles(
        self, df: pd.DataFrame, timeframe: str, report: ValidationReport
    ) -> None:
        if "timestamp" not in df.columns:
            report.add(
                Issue(
                    "missing", "warning", "No timestamp column — cannot check for missing candles"
                )
            )
            return

        ts = pd.to_datetime(df["timestamp"], errors="coerce")
        delta = TIMEFRAME_DELTAS.get(timeframe)
        if delta is None:
            report.add(
                Issue(
                    "missing",
                    "info",
                    f"Unknown timeframe '{timeframe}' — skipping missing candle check",
                )
            )
            return

        gaps = []
        for i in range(1, len(ts)):
            expected = ts.iloc[i - 1] + delta
            actual = ts.iloc[i]
            if pd.isna(expected) or pd.isna(actual):
                continue
            diff = actual - expected
            if diff > delta * 1.5:  # allow 50% tolerance
                missed = int(diff / delta) - 1
                gaps.append((i, ts.iloc[i - 1], ts.iloc[i], missed))

        for idx, prev, curr, missed in gaps:
            report.add(
                Issue(
                    "missing",
                    "critical",
                    f"Missing {missed} candle(s) between {prev} and {curr}",
                    row_index=idx,
                )
            )

    def _check_duplicates(self, df: pd.DataFrame, report: ValidationReport) -> None:
        if "timestamp" not in df.columns:
            return

        dup_mask = df.duplicated(subset=["timestamp"], keep="first")
        dup_count = dup_mask.sum()
        if dup_count > 0:
            report.add(
                Issue(
                    "duplicate",
                    "critical",
                    f"{dup_count} duplicate timestamp(s) found",
                    column="timestamp",
                )
            )

        # Check for OHLC consistency
        if all(c in df.columns for c in ["open", "high", "low", "close"]):
            bad_ohlc = (
                (df["high"] < df["low"])
                | (df["high"] < df["open"])
                | (df["high"] < df["close"])
                | (df["low"] > df["open"])
                | (df["low"] > df["close"])
            )
            bad_count = bad_ohlc.sum()
            if bad_count > 0:
                report.add(
                    Issue(
                        "duplicate",
                        "critical",
                        f"{bad_count} row(s) with OHLC inconsistency (high < low or open/close outside range)",
                        column="high/low",
                    )
                )

    def _check_oi_anomalies(
        self, df: pd.DataFrame, z_threshold: float, report: ValidationReport
    ) -> None:
        if "oi" not in df.columns or len(df) < 10:
            return

        oi = df["oi"].dropna()
        if len(oi) < 10:
            return

        # Check for negative OI
        neg_oi = (oi < 0).sum()
        if neg_oi > 0:
            report.add(
                Issue(
                    "oi",
                    "critical",
                    f"{neg_oi} row(s) with negative open interest",
                    column="oi",
                )
            )

        # Z-score anomaly detection on OI changes
        oi_changes = oi.diff().dropna()
        if len(oi_changes) < 5:
            return

        mean_change = oi_changes.mean()
        std_change = oi_changes.std()
        if std_change == 0:
            return

        z_scores = (oi_changes - mean_change) / std_change
        anomalies = z_scores[z_scores.abs() > z_threshold]
        for idx in anomalies.index:
            report.add(
                Issue(
                    "oi",
                    "warning",
                    f"OI anomaly at row {idx}: z-score={anomalies[idx]:.2f}, change={oi_changes[idx]:.0f}",
                    row_index=idx,
                    column="oi",
                )
            )

        # Check for sudden OI wipe (>90% drop in single bar)
        oi_pct = oi.pct_change()
        wipes = oi_pct[oi_pct < -0.9]
        for idx in wipes.index:
            report.add(
                Issue(
                    "oi",
                    "critical",
                    f"Sudden OI wipe at row {idx}: {oi_pct[idx] * 100:.1f}% drop",
                    row_index=idx,
                    column="oi",
                )
            )

    def _check_volume_anomalies(
        self, df: pd.DataFrame, z_threshold: float, report: ValidationReport
    ) -> None:
        if "volume" not in df.columns or len(df) < 10:
            return

        vol = df["volume"].dropna()
        if len(vol) < 10:
            return

        # Check for zero volume
        zero_vol = (vol == 0).sum()
        if zero_vol > 0:
            report.add(
                Issue(
                    "volume",
                    "warning",
                    f"{zero_vol} row(s) with zero volume",
                    column="volume",
                )
            )

        # Z-score anomaly detection
        mean_vol = vol.mean()
        std_vol = vol.std()
        if std_vol == 0:
            return

        z_scores = (vol - mean_vol) / std_vol
        anomalies = z_scores[z_scores.abs() > z_threshold]
        for idx in anomalies.index:
            report.add(
                Issue(
                    "volume",
                    "warning",
                    f"Volume anomaly at row {idx}: z-score={anomalies[idx]:.2f}, volume={vol[idx]:.0f}",
                    row_index=idx,
                    column="volume",
                )
            )

    def _check_timestamps(self, df: pd.DataFrame, timeframe: str, report: ValidationReport) -> None:
        if "timestamp" not in df.columns:
            report.add(Issue("timestamp", "warning", "No timestamp column"))
            return

        ts = pd.to_datetime(df["timestamp"], errors="coerce")

        # Check for NaT timestamps
        nat_count = ts.isna().sum()
        if nat_count > 0:
            report.add(
                Issue(
                    "timestamp",
                    "critical",
                    f"{nat_count} row(s) with invalid/unparseable timestamps",
                    column="timestamp",
                )
            )

        # Check for out-of-order timestamps
        valid_ts = ts.dropna()
        if len(valid_ts) < 2:
            return

        diffs = valid_ts.diff().dropna()
        backward = (diffs < timedelta(0)).sum()
        if backward > 0:
            report.add(
                Issue(
                    "timestamp",
                    "critical",
                    f"{backward} timestamp(s) out of order (decreasing)",
                    column="timestamp",
                )
            )

        # Check for future timestamps
        now = pd.Timestamp.now()
        future = (valid_ts > now).sum()
        if future > 0:
            report.add(
                Issue(
                    "timestamp",
                    "warning",
                    f"{future} timestamp(s) in the future",
                    column="timestamp",
                )
            )

        # Check for non-trading hours (intraday only)
        if timeframe in ("1m", "5m", "15m", "30m", "1h"):
            hours = valid_ts.dt.hour
            minutes = valid_ts.dt.minute
            weekday = valid_ts.dt.dayofweek

            # Weekend
            weekends = (weekday >= 5).sum()
            if weekends > 0:
                report.add(
                    Issue(
                        "timestamp",
                        "warning",
                        f"{weekends} timestamp(s) on weekends",
                        column="timestamp",
                    )
                )

            # Pre-market / post-market (simplified — market hours 9:15-15:30 IST)
            pre_market = (
                (hours < NSE_OPEN_HOUR) | ((hours == NSE_OPEN_HOUR) & (minutes < NSE_OPEN_MINUTE))
            ).sum()
            post_market = (
                (hours > NSE_CLOSE_HOUR)
                | ((hours == NSE_CLOSE_HOUR) & (minutes > NSE_CLOSE_MINUTE))
            ).sum()
            if pre_market > 0:
                report.add(
                    Issue(
                        "timestamp",
                        "info",
                        f"{pre_market} timestamp(s) before market open (9:15 IST)",
                        column="timestamp",
                    )
                )
            if post_market > 0:
                report.add(
                    Issue(
                        "timestamp",
                        "info",
                        f"{post_market} timestamp(s) after market close (15:30 IST)",
                        column="timestamp",
                    )
                )

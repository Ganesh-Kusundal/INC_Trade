"""Benchmark Suite — compare Dhan vs Upstox latency and throughput.

Measures: historical data, quote, option chain, depth, websocket.
Uses PaperGateway as baseline (no network).

Usage:
    from brokers.common.services.benchmark import BenchmarkSuite

    suite = BenchmarkSuite()
    results = suite.run(symbols=["RELIANCE", "TCS"], iterations=5)
    suite.print_report(results)

CLI:
    tradex benchmark [--iterations 5] [--symbols RELIANCE,TCS]
"""

from __future__ import annotations

import logging
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Result of a single benchmark test."""

    test_name: str
    broker: str
    symbol: str
    latency_ms: float = 0.0
    success: bool = True
    error: str = ""
    throughput: float = 0.0  # ops/sec for batch tests
    metadata: dict = field(default_factory=dict)


@dataclass
class BenchmarkReport:
    """Aggregated benchmark report across all tests."""

    results: list[BenchmarkResult] = field(default_factory=list)
    broker_summaries: dict = field(default_factory=dict)

    def add(self, result: BenchmarkResult) -> None:
        self.results.append(result)
        broker = result.broker
        if broker not in self.broker_summaries:
            self.broker_summaries[broker] = {
                "tests": 0,
                "passed": 0,
                "failed": 0,
                "latencies": [],
            }
        summary = self.broker_summaries[broker]
        summary["tests"] += 1
        if result.success:
            summary["passed"] += 1
            summary["latencies"].append(result.latency_ms)
        else:
            summary["failed"] += 1

    def compute_summaries(self) -> None:
        """Compute avg/p50/p95/p99 latencies per broker."""
        for _broker, summary in self.broker_summaries.items():
            lats = sorted(summary["latencies"])
            if not lats:
                summary["avg_ms"] = 0
                summary["p50_ms"] = 0
                summary["p95_ms"] = 0
                summary["p99_ms"] = 0
                continue
            summary["avg_ms"] = statistics.mean(lats)
            summary["p50_ms"] = statistics.median(lats)
            n = len(lats)
            summary["p95_ms"] = lats[int(n * 0.95)] if n >= 2 else lats[-1]
            summary["p99_ms"] = lats[int(n * 0.99)] if n >= 2 else lats[-1]


class BenchmarkSuite:
    """Runs benchmarks against broker gateways."""

    def __init__(self) -> None:
        self._gateways: dict[str, Any] = {}

    def register(self, name: str, gateway: Any) -> None:
        """Register a gateway for benchmarking."""
        self._gateways[name] = gateway

    def run(
        self,
        symbols: list[str] | None = None,
        iterations: int = 5,
        tests: list[str] | None = None,
        timeframe: str = "1d",
        lookback_days: int = 30,
    ) -> BenchmarkReport:
        """Run all benchmark tests.

        Parameters
        ----------
        symbols : list of str
            Symbols to test (default: ["RELIANCE"]).
        iterations : int
            Number of iterations per test.
        tests : list of str or None
            Specific tests to run (default: all).
        timeframe : str
            Timeframe for historical data test.
        lookback_days : int
            Days of historical data to fetch.
        """
        if not symbols:
            symbols = ["RELIANCE"]

        report = BenchmarkReport()
        all_tests = tests or [
            "historical",
            "quote",
            "ltp",
            "depth",
            "option_chain",
            "future_chain",
            "search",
        ]

        for broker_name, gw in self._gateways.items():
            for symbol in symbols:
                for test_name in all_tests:
                    method = getattr(self, f"_bench_{test_name}", None)
                    if method is None:
                        continue

                    result = BenchmarkResult(
                        test_name=test_name,
                        broker=broker_name,
                        symbol=symbol,
                    )

                    try:
                        stats = method(gw, symbol, iterations, timeframe, lookback_days)
                        result.latency_ms = stats["avg_ms"]
                        result.throughput = stats.get("throughput", 0.0)
                        result.metadata = stats
                        result.success = True
                    except Exception as exc:
                        result.success = False
                        result.error = str(exc)
                        logger.warning(
                            "Benchmark %s/%s/%s failed: %s", broker_name, test_name, symbol, exc
                        )

                    report.add(result)

        report.compute_summaries()
        return report

    # ── Individual benchmarks ─────────────────────────────────────────

    def _bench_historical(
        self, gw: Any, symbol: str, iterations: int, timeframe: str, lookback_days: int
    ) -> dict:
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            gw.history(symbol, timeframe=timeframe, lookback_days=lookback_days)
            latencies.append((time.perf_counter() - t0) * 1000)
        return self._stats(latencies)

    def _bench_quote(self, gw: Any, symbol: str, iterations: int, *args: Any) -> dict:
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            gw.quote(symbol)
            latencies.append((time.perf_counter() - t0) * 1000)
        return self._stats(latencies)

    def _bench_ltp(self, gw: Any, symbol: str, iterations: int, *args: Any) -> dict:
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            gw.ltp(symbol)
            latencies.append((time.perf_counter() - t0) * 1000)
        return self._stats(latencies)

    def _bench_depth(self, gw: Any, symbol: str, iterations: int, *args: Any) -> dict:
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            gw.depth(symbol)
            latencies.append((time.perf_counter() - t0) * 1000)
        return self._stats(latencies)

    def _bench_option_chain(self, gw: Any, symbol: str, iterations: int, *args: Any) -> dict:
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            gw.option_chain(symbol)
            latencies.append((time.perf_counter() - t0) * 1000)
        return self._stats(latencies)

    def _bench_future_chain(self, gw: Any, symbol: str, iterations: int, *args: Any) -> dict:
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            gw.future_chain(symbol)
            latencies.append((time.perf_counter() - t0) * 1000)
        return self._stats(latencies)

    def _bench_search(self, gw: Any, symbol: str, iterations: int, *args: Any) -> dict:
        latencies = []
        for _ in range(iterations):
            t0 = time.perf_counter()
            gw.search(symbol)
            latencies.append((time.perf_counter() - t0) * 1000)
        return self._stats(latencies)

    @staticmethod
    def _stats(latencies: list[float]) -> dict:
        """Compute latency statistics."""
        sorted_lats = sorted(latencies)
        n = len(sorted_lats)
        return {
            "avg_ms": statistics.mean(sorted_lats),
            "min_ms": sorted_lats[0],
            "max_ms": sorted_lats[-1],
            "p50_ms": statistics.median(sorted_lats),
            "p95_ms": sorted_lats[int(n * 0.95)] if n >= 2 else sorted_lats[-1],
            "p99_ms": sorted_lats[int(n * 0.99)] if n >= 2 else sorted_lats[-1],
            "throughput": 1000.0 / statistics.mean(sorted_lats)
            if statistics.mean(sorted_lats) > 0
            else 0,
            "iterations": n,
        }

    @staticmethod
    def print_report(report: BenchmarkReport) -> str:
        """Generate a formatted report string."""
        lines = ["=" * 70, "BENCHMARK REPORT", "=" * 70, ""]

        # Per-broker summary
        for broker, summary in sorted(report.broker_summaries.items()):
            lines.append(f"Broker: {broker}")
            lines.append(
                f"  Tests: {summary['tests']} | Passed: {summary['passed']} | Failed: {summary['failed']}"
            )
            if summary["latencies"]:
                lines.append(
                    f"  Latency: avg={summary['avg_ms']:.1f}ms  p50={summary['p50_ms']:.1f}ms  p95={summary['p95_ms']:.1f}ms  p99={summary['p99_ms']:.1f}ms"
                )
            lines.append("")

        # Per-test breakdown
        lines.append("-" * 70)
        lines.append(
            f"{'Test':<20} {'Broker':<10} {'Symbol':<12} {'Avg(ms)':>10} {'P50(ms)':>10} {'P95(ms)':>10} {'Status':>8}"
        )
        lines.append("-" * 70)

        for r in report.results:
            status = "OK" if r.success else "FAIL"
            avg = f"{r.latency_ms:.1f}" if r.success else r.error[:10]
            lines.append(
                f"{r.test_name:<20} {r.broker:<10} {r.symbol:<12} {avg:>10} {r.metadata.get('p50_ms', 0):>10.1f} {r.metadata.get('p95_ms', 0):>10.1f} {status:>8}"
            )

        lines.append("=" * 70)
        return "\n".join(lines)

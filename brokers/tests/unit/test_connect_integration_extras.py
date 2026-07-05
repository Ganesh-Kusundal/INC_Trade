"""End-to-end integration tests for ``brokers.connect()`` with all extras."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path


def _write_csv(path: str) -> None:
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "exchange", "timestamp", "open", "high", "low", "close", "volume"])
        w.writerow(
            [
                "RELIANCE",
                "NSE",
                "2024-01-02 09:15:00",
                "2500.00",
                "2510.00",
                "2495.00",
                "2505.00",
                "500000",
            ]
        )


class TestConnectExtras:
    def test_connect_paper_returns_session_with_extras(self) -> None:
        import brokers

        broker = brokers.connect("paper")
        try:
            assert broker.scanner is not None
            assert broker.replay is not None
            assert broker.degraded_mode is not None
            assert broker.analytics is not None
        finally:
            broker.close()

    def test_scanner_finds_instruments(self) -> None:
        from decimal import Decimal

        import brokers

        broker = brokers.connect("paper")
        try:
            # Register the instrument first so the scanner can find it
            broker.market.instrument("RELIANCE")
            from inc_trade.market.scanner import PriceAbove

            result = broker.scanner.scan(PriceAbove(Decimal("0")))
            assert result.total_scanned >= 1
            assert any(i.symbol == "RELIANCE" for i, _ in result.matched)
        finally:
            broker.close()

    def test_replay_loads_csv(self) -> None:
        import brokers

        broker = brokers.connect("paper")
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                fp = str(Path(tmpdir) / "data.csv")
                _write_csv(fp)
                broker.replay.load_csv(fp)
                assert "NSE:RELIANCE" in broker.replay.symbols()
        finally:
            broker.close()

    def test_degraded_mode_tracks_failures(self) -> None:
        import brokers

        broker = brokers.connect("paper")
        try:
            dm = broker.degraded_mode
            dm.enter_degraded("NSE:RELIANCE")
            assert "NSE:RELIANCE" in dm.degraded_keys()
            dm.recover("NSE:RELIANCE")
            assert "NSE:RELIANCE" not in dm.degraded_keys()
        finally:
            broker.close()

    def test_analytics_calculators_usable(self) -> None:
        import brokers
        from inc_trade.domain.entities import Trade
        from inc_trade.domain.enums import Side

        broker = brokers.connect("paper")
        try:
            vwap = broker.analytics.vwap()
            vwap.update(
                Trade(
                    trade_id="T1",
                    order_id="O1",
                    symbol="RELIANCE",
                    exchange="NSE",
                    side=Side.BUY,
                    quantity=10,
                    price=__import__("decimal").Decimal("100"),
                )
            )
            assert vwap.value > 0
        finally:
            broker.close()

    def test_instrument_enhanced_methods(self) -> None:
        import brokers

        broker = brokers.connect("paper")
        try:
            inst = broker.market.instrument("RELIANCE")._instrument
            meta = inst.metadata()
            assert meta["symbol"] == "RELIANCE"
            assert meta["exchange"] == "NSE"
            status = inst.market_status()
            assert status in ("open", "closed", "unknown")
        finally:
            broker.close()

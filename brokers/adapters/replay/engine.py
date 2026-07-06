"""Replay engine — replays historical data through market-data ports.

Implements ``MarketDataPort``, ``HistoricalPort``, ``StreamingPort`` and
``HistoricalProvider`` so it can be plugged in transparently wherever a
broker adapter is used.

Speed control:
- ``speed == 0`` → instant (backtest mode; all ticks dispatched immediately)
- ``speed == 1.0`` → real-time (sleep proportional to tick deltas)
- ``speed > 1.0`` → accelerated

Connection wiring (the wiring code can register the engine in
``HistoricalRouter`` as a provider just like a broker adapter).
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from inc_trade.domain.entities import Candle, MarketDepth, Quote

from brokers.adapters.replay.sources import CsvSource
from brokers.adapters.replay.tick_source import TickSource

logger = logging.getLogger(__name__)

_DEPTH_BID_LEVELS = 5
_DEPTH_ASK_LEVELS = 5


def _build_synthetic_depth(symbol: str, exchange: str, ltp: Decimal) -> MarketDepth:
    """Create a minimal 5-level synthetic depth around LTP."""
    from inc_trade.domain.entities import DepthLevel

    tick = Decimal("0.05")
    bids = tuple(
        DepthLevel(price=ltp - tick * Decimal(i + 1), quantity=100 * (i + 1), orders=10)
        for i in range(_DEPTH_BID_LEVELS)
    )
    asks = tuple(
        DepthLevel(price=ltp + tick * Decimal(i + 1), quantity=100 * (i + 1), orders=10)
        for i in range(_DEPTH_ASK_LEVELS)
    )
    return MarketDepth(symbol=symbol, exchange=exchange, bids=bids, asks=asks)


class ReplayEngine:
    """Replays historical data through market-data port interfaces.

    Args:
        speed: Time-acceleration factor. ``0`` = instant, ``1.0`` = real-time.
        csv_dir: Optional directory of CSV files to auto-load.
        tick_jitter_bps: Basis-points jitter for synthetic ticks.
    """

    def __init__(
        self,
        speed: float = 1.0,
        csv_dir: str | None = None,
        tick_jitter_bps: int = 5,
    ) -> None:
        self._speed = max(0.0, float(speed))
        self._csv_dir = csv_dir
        self._tick_jitter_bps = tick_jitter_bps

        self._candles_by_key: dict[str, list[Candle]] = {}
        self._quotes_by_key: dict[str, list[Quote]] = {}

        self._csv_source = CsvSource()
        self._tick_source = TickSource(jitter_bps=tick_jitter_bps)

        self._connected = False
        self._stream_tasks: list[asyncio.Task[Any]] = []
        self._callbacks: dict[str, list[Callable[[Any], None]]] = defaultdict(list)
        self._active_subscriptions: set[tuple[str, str]] = set()

        if csv_dir is not None:
            self._load_csv_dir(csv_dir)

    # ── Speed control ─────────────────────────────────────────────────

    @property
    def speed(self) -> float:
        """Current speed factor."""
        return self._speed

    @speed.setter
    def speed(self, value: float) -> None:
        self._speed = max(0.0, float(value))

    # ── Data loading ──────────────────────────────────────────────────

    def load_csv(self, filepath: str) -> None:
        """Load candles from a CSV file.

        Args:
            filepath: Path to CSV file.
        """
        loaded = self._csv_source.load(filepath)
        for key, candles in loaded.items():
            self._candles_by_key.setdefault(key, []).extend(candles)
        self._refresh_quotes()

    def _load_csv_dir(self, csv_dir: str) -> None:
        from pathlib import Path

        path = Path(csv_dir)
        if not path.exists():
            logger.warning("ReplayEngine: CSV dir does not exist: %s", csv_dir)
            return
        for csv_file in path.glob("*.csv"):
            try:
                self.load_csv(str(csv_file))
            except Exception as exc:
                logger.warning("ReplayEngine: failed to load %s: %s", csv_file, exc)

    def _refresh_quotes(self) -> None:
        """Re-generate the quote cache from the latest candle per symbol."""
        for key, candles in self._candles_by_key.items():
            if not candles:
                continue
            exchange, _, symbol = key.partition(":")
            quotes = list(self._tick_source.generate(symbol, exchange, candles[-1:]))
            if quotes:
                self._quotes_by_key[key] = quotes

    # ── Symbol / instrument helpers ───────────────────────────────────

    def symbols(self) -> list[str]:
        """List available composite keys."""
        return list(self._candles_by_key.keys())

    def has_symbol(self, symbol: str, exchange: str = "NSE") -> bool:
        """Check if a symbol is loaded."""
        return f"{exchange}:{symbol}" in self._candles_by_key

    # ── MarketDataPort ────────────────────────────────────────────────

    def ltp(self, symbol: str, exchange: str = "NSE") -> Decimal:
        quotes = self._quotes_by_key.get(f"{exchange}:{symbol}", [])
        if not quotes:
            raise KeyError(f"No data for {exchange}:{symbol}")
        return quotes[-1].ltp

    def quote(self, symbol: str, exchange: str = "NSE") -> Quote:
        quotes = self._quotes_by_key.get(f"{exchange}:{symbol}", [])
        if not quotes:
            raise KeyError(f"No data for {exchange}:{symbol}")
        return quotes[-1]

    def depth(self, symbol: str, exchange: str = "NSE") -> MarketDepth:
        quote = self.quote(symbol, exchange)
        return _build_synthetic_depth(symbol, exchange, quote.ltp)

    def ltp_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Decimal]:
        return {sym: self.ltp(sym, exchange) for sym in symbols if self.has_symbol(sym, exchange)}

    def quote_batch(self, symbols: list[str], exchange: str = "NSE") -> dict[str, Quote]:
        return {sym: self.quote(sym, exchange) for sym in symbols if self.has_symbol(sym, exchange)}

    # ── HistoricalPort / HistoricalProvider ───────────────────────────

    def get_historical_candles(
        self,
        symbol: str,
        exchange: str,
        start_time: datetime,
        end_time: datetime,
        resolution: str,
    ) -> list[Candle]:
        candles = self._candles_by_key.get(f"{exchange}:{symbol}", [])

        def _aware(ts: datetime) -> datetime:
            return ts if ts.tzinfo else ts.replace(tzinfo=UTC)

        s = _aware(start_time)
        e = _aware(end_time)
        return [c for c in candles if s <= _aware(c.timestamp) <= e]

    @property
    def provider_id(self) -> str:
        return "replay"

    @property
    def is_available(self) -> bool:
        return True

    # ── StreamingPort ─────────────────────────────────────────────────

    async def connect(self) -> None:
        self._connected = True
        logger.info("ReplayEngine: connected (speed=%.2f)", self._speed)

    async def disconnect(self) -> None:
        for task in self._stream_tasks:
            task.cancel()
        self._stream_tasks.clear()
        self._active_subscriptions.clear()
        self._callbacks.clear()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def subscribe_quotes(
        self,
        symbols: list[str],
        exchange: str,
        callback: Callable[[Any], None],
    ) -> None:
        if not self._connected:
            await self.connect()
        for symbol in symbols:
            key = f"{exchange}:{symbol}"
            self._active_subscriptions.add((exchange, symbol))
            if callback not in self._callbacks[key]:
                self._callbacks[key].append(callback)
        # launch a single replay task per unique (exchange, symbol)
        for symbol in symbols:
            if any(
                task.get_name() == f"replay-{exchange}:{symbol}" and not task.done()
                for task in self._stream_tasks
            ):
                continue
            task = asyncio.create_task(
                self._replay_symbol(symbol, exchange),
                name=f"replay-{exchange}:{symbol}",
            )
            self._stream_tasks.append(task)

    async def unsubscribe_quotes(self, symbols: list[str], exchange: str) -> None:
        for symbol in symbols:
            self._active_subscriptions.discard((exchange, symbol))
            key = f"{exchange}:{symbol}"
            self._callbacks.pop(key, None)
        for task in list(self._stream_tasks):
            name = task.get_name()
            if any(name.endswith(f"{exchange}:{sym}") for sym in symbols) and not task.done():
                task.cancel()
                self._stream_tasks.remove(task)

    async def _replay_symbol(self, symbol: str, exchange: str) -> None:
        key = f"{exchange}:{symbol}"
        quotes = self._quotes_by_key.get(key, [])
        prev_ts: datetime | None = None
        for quote in quotes:
            if self._speed > 0 and prev_ts is not None:
                delta = (quote.timestamp - prev_ts).total_seconds()
                if delta > 0:
                    await asyncio.sleep(delta / self._speed)
            for cb in list(self._callbacks.get(key, [])):
                try:
                    cb(quote)
                except Exception as exc:
                    logger.warning("ReplayEngine: callback error: %s", exc)
            prev_ts = quote.timestamp

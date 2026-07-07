"""Market data domain — quotes, OHLCV, depth, option chain."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Optional


@dataclass
class DepthLevel:
    """Single level in the order book.

    Represents one price level on both the bid (buy) and ask (sell)
    side of the order book.

    Attributes:
        bid_price: Best bid price at this level.
        bid_quantity: Total quantity bid at this level.
        bid_orders: Number of orders at this bid level.
        ask_price: Best ask price at this level.
        ask_quantity: Total quantity offered at this level.
        ask_orders: Number of orders at this ask level.
    """

    bid_price: Decimal = Decimal("0")
    bid_quantity: int = 0
    bid_orders: int = 0
    ask_price: Decimal = Decimal("0")
    ask_quantity: int = 0
    ask_orders: int = 0


@dataclass
class MarketDepth:
    """Order book depth for an instrument.

    Contains multiple price levels showing bid and ask quantities.
    Dhan supports 20 levels (standard) or 200 levels (premium).

    Attributes:
        security_id: Broker-assigned security ID.
        exchange: Exchange segment string.
        levels: List of DepthLevel entries, ordered by price.
        timestamp: When the depth snapshot was taken.

    Properties:
        best_bid: The top bid level (highest bid).
        best_ask: The top ask level (lowest ask).
        spread: Difference between best ask and best bid.
        total_bid_quantity: Sum of all bid quantities.
        total_ask_quantity: Sum of all ask quantities.
    """

    security_id: str = ""
    exchange: str = ""
    levels: list[DepthLevel] = field(default_factory=list)
    timestamp: Optional[datetime] = None

    @property
    def best_bid(self) -> Optional[DepthLevel]:
        """The top bid level (highest buy price).

        Returns:
            The first DepthLevel if levels exist, else None.
        """
        return self.levels[0] if self.levels else None

    @property
    def best_ask(self) -> Optional[DepthLevel]:
        """The top ask level (lowest sell price).

        Returns:
            The first DepthLevel if levels exist, else None.
        """
        return self.levels[0] if self.levels else None

    @property
    def spread(self) -> Optional[Decimal]:
        """Bid-ask spread at the top of the book.

        Returns:
            The spread (ask - bid) as a Decimal, or None if
            no ask price is available.
        """
        if self.levels and self.levels[0].ask_price > 0:
            return self.levels[0].ask_price - self.levels[0].bid_price
        return None

    @property
    def total_bid_quantity(self) -> int:
        """Sum of all bid quantities across all levels.

        Returns:
            Total quantity on the bid side.
        """
        return sum(lvl.bid_quantity for lvl in self.levels)

    @property
    def total_ask_quantity(self) -> int:
        """Sum of all ask quantities across all levels.

        Returns:
            Total quantity on the ask side.
        """
        return sum(lvl.ask_quantity for lvl in self.levels)


@dataclass
class OHLCV:
    """Open-High-Low-Close-Volume candle bar.

    Represents a single price bar for a given time period.
    Used for both daily and intraday historical data.

    Attributes:
        timestamp: Bar timestamp (UTC).
        open: Opening price.
        high: Highest price during the period.
        low: Lowest price during the period.
        close: Closing price.
        volume: Total volume traded.
        open_interest: Open interest (for derivatives only).
    """

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    open_interest: Optional[int] = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], index: int = 0) -> OHLCV:
        """Construct an OHLCV from Dhan historical data arrays.

        Dhan returns historical data as parallel arrays (timestamps,
        opens, highs, etc.). This method extracts a single candle
        at the given index.

        Args:
            data: Dict with parallel arrays for timestamp, open,
                high, low, close, volume, and open_interest.
            index: Index into the arrays to extract.

        Returns:
            Populated OHLCV candle.
        """
        ts_raw = data.get("timestamp", [])
        o_raw = data.get("open", [])
        h_raw = data.get("high", [])
        l_raw = data.get("low", [])
        c_raw = data.get("close", [])
        v_raw = data.get("volume", [])
        oi_raw = data.get("open_interest", [])

        ts = ts_raw[index] if index < len(ts_raw) else 0
        if isinstance(ts, (int, float)):
            from datetime import timezone

            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            dt = datetime.now()

        return cls(
            timestamp=dt,
            open=Decimal(str(o_raw[index] if index < len(o_raw) else 0)),
            high=Decimal(str(h_raw[index] if index < len(h_raw) else 0)),
            low=Decimal(str(l_raw[index] if index < len(l_raw) else 0)),
            close=Decimal(str(c_raw[index] if index < len(c_raw) else 0)),
            volume=int(v_raw[index] if index < len(v_raw) else 0),
            open_interest=int(oi_raw[index]) if oi_raw and index < len(oi_raw) else None,
        )


@dataclass
class Quote:
    """Real-time quote snapshot for an instrument.

    Contains the latest market data including last traded price,
    OHLC for the day, bid/ask, volume, and circuit limits.

    Attributes:
        security_id: Broker-assigned security ID.
        exchange: Exchange segment string.
        last_price: Last traded price.
        average_price: Volume-weighted average price.
        bid_price: Best bid (buy) price.
        bid_quantity: Quantity at best bid.
        ask_price: Best ask (sell) price.
        ask_quantity: Quantity at best ask.
        last_quantity: Quantity of last trade.
        volume: Total day volume.
        open_interest: Current OI (derivatives only).
        open: Day opening price.
        high: Day high.
        low: Day low.
        close: Previous day closing price.
        upper_circuit: Upper circuit limit.
        lower_circuit: Lower circuit limit.
        net_change: Absolute price change.
        last_trade_time: Timestamp of last trade.
        depth: Order book depth (if requested).
        raw: Raw broker response data.
    """

    security_id: str = ""
    trading_symbol: str = ""
    exchange: str = ""
    exchange_segment: str = ""
    last_price: Decimal = Decimal("0")
    average_price: Decimal = Decimal("0")
    bid_price: Decimal = Decimal("0")
    bid_quantity: int = 0
    ask_price: Decimal = Decimal("0")
    ask_quantity: int = 0
    last_quantity: int = 0
    volume: int = 0
    open_interest: Optional[int] = None
    open: Decimal = Decimal("0")
    high: Decimal = Decimal("0")
    low: Decimal = Decimal("0")
    close: Decimal = Decimal("0")
    upper_circuit: Decimal = Decimal("0")
    lower_circuit: Decimal = Decimal("0")
    net_change: Decimal = Decimal("0")
    last_trade_time: Optional[datetime] = None
    depth: Optional[MarketDepth] = None
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dhan_ticker(cls, data: dict[str, Any]) -> Quote:
        """Construct from Dhan ticker_data response.

        The ticker endpoint returns minimal data (last price only).
        For full quote data, use from_dhan_quote() instead.

        Args:
            data: Raw dict from Dhan ticker_data API.

        Returns:
            Quote with last_price populated.
        """
        return cls(
            last_price=Decimal(str(data.get("last_price", 0))),
            raw=data,
        )

    @classmethod
    def from_dhan_quote(cls, exchange: str, sec_id: str, data: dict[str, Any]) -> Quote:
        """Construct from Dhan quote_data response.

        The quote endpoint returns full market data including
        OHLC, depth, and circuit limits.

        Args:
            exchange: Exchange segment string.
            sec_id: Security ID.
            data: Raw dict from Dhan quote_data API.

        Returns:
            Fully populated Quote.
        """
        return cls(
            security_id=sec_id,
            exchange=exchange,
            last_price=Decimal(str(data.get("last_price", 0))),
            average_price=Decimal(str(data.get("average_price", 0))),
            bid_price=Decimal(str(data.get("top_bid_price", 0))),
            bid_quantity=int(data.get("top_bid_quantity", 0)),
            ask_price=Decimal(str(data.get("top_ask_price", 0))),
            ask_quantity=int(data.get("top_ask_quantity", 0)),
            last_quantity=int(data.get("last_quantity", 0)),
            volume=int(data.get("volume", 0)),
            open_interest=data.get("oi"),
            open=Decimal(str(data.get("ohlc", {}).get("open", 0))),
            high=Decimal(str(data.get("ohlc", {}).get("high", 0))),
            low=Decimal(str(data.get("ohlc", {}).get("low", 0))),
            close=Decimal(str(data.get("ohlc", {}).get("close", 0))),
            upper_circuit=Decimal(str(data.get("upper_circuit_limit", 0))),
            lower_circuit=Decimal(str(data.get("lower_circuit_limit", 0))),
            net_change=Decimal(str(data.get("net_change", 0))),
            raw=data,
        )

    @property
    def change_pct(self) -> Decimal:
        """Percentage change from previous close.

        Calculates ((last_price - close) / close) * 100.

        Returns:
            Percentage change as a Decimal. Returns 0 if
            previous close is unavailable.
        """
        if self.close > 0:
            return ((self.last_price - self.close) / self.close) * 100
        return Decimal("0")


@dataclass
class OptionGreeks:
    """Option Greeks — risk sensitivity metrics.

    Standard Black-Scholes Greeks for option pricing and risk
    management.

    Attributes:
        delta: Rate of change of option price w.r.t. underlying.
        gamma: Rate of change of delta w.r.t. underlying.
        theta: Time decay per day.
        vega: Sensitivity to volatility changes.
        rho: Sensitivity to interest rate changes.
    """

    delta: Decimal = Decimal("0")
    gamma: Decimal = Decimal("0")
    theta: Decimal = Decimal("0")
    vega: Decimal = Decimal("0")
    rho: Decimal = Decimal("0")


@dataclass
class OptionQuote:
    """Single option contract quote within a chain.

    Contains full quote data for one option contract (CE or PE)
    at a specific strike and expiry.

    Attributes:
        security_id: Broker-assigned option security ID.
        last_price: Last traded price of this option.
        average_price: VWAP of this option.
        bid_price: Best bid price.
        bid_quantity: Quantity at best bid.
        ask_price: Best ask price.
        ask_quantity: Quantity at best ask.
        volume: Total day volume.
        open_interest: Current open interest.
        oi_change: Change in OI from previous close.
        implied_volatility: Implied volatility.
        greeks: Option Greeks (delta, gamma, theta, vega, rho).
    """

    security_id: str = ""
    last_price: Decimal = Decimal("0")
    average_price: Decimal = Decimal("0")
    bid_price: Decimal = Decimal("0")
    bid_quantity: int = 0
    ask_price: Decimal = Decimal("0")
    ask_quantity: int = 0
    volume: int = 0
    open_interest: int = 0
    oi_change: int = 0
    implied_volatility: Decimal = Decimal("0")
    greeks: OptionGreeks = field(default_factory=OptionGreeks)

    @classmethod
    def from_dhan(cls, data: dict[str, Any]) -> OptionQuote:
        """Construct from Dhan option chain response.

        Args:
            data: Raw dict from Dhan option_chain for a single
                CE or PE leg.

        Returns:
            Populated OptionQuote with Greeks.
        """
        greeks_data = data.get("greeks", {})
        return cls(
            security_id=str(data.get("security_id", "")),
            last_price=Decimal(str(data.get("last_price", 0))),
            average_price=Decimal(str(data.get("average_price", 0))),
            bid_price=Decimal(str(data.get("top_bid_price", 0))),
            bid_quantity=int(data.get("top_bid_quantity", 0)),
            ask_price=Decimal(str(data.get("top_ask_price", 0))),
            ask_quantity=int(data.get("top_ask_quantity", 0)),
            volume=int(data.get("volume", 0)),
            open_interest=int(data.get("oi", 0)),
            oi_change=int(data.get("oi_change", 0)),
            implied_volatility=Decimal(str(data.get("implied_volatility", 0))),
            greeks=OptionGreeks(
                delta=Decimal(str(greeks_data.get("delta", 0))),
                gamma=Decimal(str(greeks_data.get("gamma", 0))),
                theta=Decimal(str(greeks_data.get("theta", 0))),
                vega=Decimal(str(greeks_data.get("vega", 0))),
            ),
        )


@dataclass
class OptionStrike:
    """A single strike in the option chain.

    Puts the call and put option quotes side by side for
    a given strike price.

    Attributes:
        strike: Strike price.
        call: Call option quote (CE). May be None.
        put: Put option quote (PE). May be None.
    """

    strike: Decimal = Decimal("0")
    call: Optional[OptionQuote] = None
    put: Optional[OptionQuote] = None


@dataclass
class OptionChain:
    """Full option chain for an underlying.

    Contains all strikes with call and put quotes for a given
    underlying and expiry. Provides analytical methods for
    finding ATM strikes, computing PCR, and aggregating OI.

    Attributes:
        underlying_security_id: Security ID of the underlying.
        underlying_symbol: Symbol of the underlying.
        spot_price: Current spot/last price of the underlying.
        expiry: Expiry date string (YYYY-MM-DD).
        strikes: List of OptionStrike objects, sorted by strike.
        raw: Raw broker response data.
    """

    underlying_security_id: str = ""
    underlying_symbol: str = ""
    spot_price: Decimal = Decimal("0")
    expiry: str = ""
    strikes: list[OptionStrike] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dhan(cls, data: dict[str, Any], expiry: str = "") -> OptionChain:
        """Construct from Dhan option_chain response.

        Parses the nested Dhan response format where strikes are
        keyed by strike price string under data["oc"].

        Args:
            data: Raw dict from Dhan option_chain API.
            expiry: Expiry date string.

        Returns:
            Populated OptionChain with all strikes.
        """
        inner = data.get("data", data)
        oc_data = inner.get("oc", {})

        strikes = []
        for strike_str, legs in sorted(oc_data.items(), key=lambda x: float(x[0])):
            call = OptionQuote.from_dhan(legs.get("ce", {})) if legs.get("ce") else None
            put = OptionQuote.from_dhan(legs.get("pe", {})) if legs.get("pe") else None
            strikes.append(
                OptionStrike(
                    strike=Decimal(strike_str),
                    call=call,
                    put=put,
                )
            )

        return cls(
            spot_price=Decimal(str(inner.get("last_price", 0))),
            expiry=expiry,
            strikes=strikes,
            raw=data,
        )

    @property
    def calls(self) -> list[OptionQuote]:
        """All call option quotes in the chain.

        Returns:
            List of OptionQuote for CE options.
        """
        return [s.call for s in self.strikes if s.call]

    @property
    def puts(self) -> list[OptionQuote]:
        """All put option quotes in the chain.

        Returns:
            List of OptionQuote for PE options.
        """
        return [s.put for s in self.strikes if s.put]

    def find_strike(self, strike: Decimal) -> Optional[OptionStrike]:
        """Find a specific strike in the chain.

        Args:
            strike: The strike price to find.

        Returns:
            OptionStrike if found, None otherwise.
        """
        for s in self.strikes:
            if s.strike == strike:
                return s
        return None

    def find_atm(self, spot: Optional[Decimal] = None) -> Optional[OptionStrike]:
        """Find the ATM strike closest to the spot price.

        The ATM strike is the one with the smallest absolute
        difference from the underlying's spot price.

        Args:
            spot: Override spot price. If None, uses the
                chain's spot_price attribute.

        Returns:
            The closest OptionStrike, or None if no strikes.
        """
        """Find the ATM strike closest to spot price."""
        target = spot or self.spot_price
        if not self.strikes:
            return None
        return min(self.strikes, key=lambda s: abs(s.strike - target))

    @property
    def total_call_oi(self) -> int:
        """Total open interest across all call options.

        Returns:
            Sum of CE open interest at all strikes.
        """
        return sum(s.call.open_interest for s in self.strikes if s.call)

    @property
    def total_put_oi(self) -> int:
        """Total open interest across all put options.

        Returns:
            Sum of PE open interest at all strikes.
        """
        return sum(s.put.open_interest for s in self.strikes if s.put)

    @property
    def pcr(self) -> Decimal:
        """Put-Call Ratio by open interest.

        PCR = total_put_oi / total_call_oi. Values > 1.2 suggest
        bullish sentiment (high put writing), < 0.8 suggest bearish.

        Returns:
            PCR as a Decimal. Returns 0 if call OI is zero.
        """
        call_oi = self.total_call_oi
        if call_oi == 0:
            return Decimal("0")
        return Decimal(str(self.total_put_oi)) / Decimal(str(call_oi))


@dataclass
class HistoricalSeries:
    """Time series of OHLCV bars for an instrument.

    Wraps a list of OHLCV bars with instrument metadata and
    provides convenient access patterns for analysis.

    Attributes:
        instrument_id: Security ID of the instrument.
        exchange: Exchange segment.
        bars: List of OHLCV bars in chronological order.
        interval: Bar interval (e.g., "1D", "5m", "1h").
    """

    instrument_id: str = ""
    exchange: str = ""
    bars: list[OHLCV] = field(default_factory=list)
    interval: str = "1D"

    @property
    def count(self) -> int:
        """Number of bars in the series."""
        return len(self.bars)

    @property
    def start_date(self) -> Optional[datetime]:
        """Timestamp of the first bar."""
        return self.bars[0].timestamp if self.bars else None

    @property
    def end_date(self) -> Optional[datetime]:
        """Timestamp of the last bar."""
        return self.bars[-1].timestamp if self.bars else None

    @property
    def first(self) -> Optional[OHLCV]:
        """First bar in the series."""
        return self.bars[0] if self.bars else None

    @property
    def last(self) -> Optional[OHLCV]:
        """Last bar in the series."""
        return self.bars[-1] if self.bars else None

    @property
    def highs(self) -> list[Decimal]:
        """All high prices."""
        return [b.high for b in self.bars]

    @property
    def lows(self) -> list[Decimal]:
        """All low prices."""
        return [b.low for b in self.bars]

    @property
    def closes(self) -> list[Decimal]:
        """All close prices."""
        return [b.close for b in self.bars]

    @property
    def volumes(self) -> list[int]:
        """All volume values."""
        return [b.volume for b in self.bars]

    @property
    def price_range(self) -> tuple[Decimal, Decimal]:
        """Overall (min_low, max_high) range."""
        if not self.bars:
            return (Decimal("0"), Decimal("0"))
        return (min(b.low for b in self.bars), max(b.high for b in self.bars))

    @property
    def total_volume(self) -> int:
        """Sum of all bar volumes."""
        return sum(b.volume for b in self.bars)

    def slice(self, start_idx: int = 0, end_idx: Optional[int] = None) -> HistoricalSeries:
        """Return a sub-series from start_idx to end_idx."""
        sliced = self.bars[start_idx:end_idx]
        return HistoricalSeries(
            instrument_id=self.instrument_id,
            exchange=self.exchange,
            bars=sliced,
            interval=self.interval,
        )

    def __len__(self) -> int:
        return len(self.bars)

    def __iter__(self):
        return iter(self.bars)

    def __getitem__(self, index):
        return self.bars[index]

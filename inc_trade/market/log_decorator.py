"""LoggedDecorator — logs all instrument method calls for debugging.

Useful during development and troubleshooting to trace every
interaction with a specific instrument::

    from inc_trade.market.log_decorator import LoggedDecorator

    inst = LoggedDecorator(base_instrument)
    inst.quote()   # → "logged: quote() called for NSE:RELIANCE"
    inst.buy(10)   # → "logged: buy(10) called for NSE:RELIANCE"

Combine with other decorators::

    inst = with_logging(with_cache(with_depth(base, 200)))
"""

from __future__ import annotations

import logging
from typing import Any

from inc_trade.market.decorators import InstrumentDecorator

logger = logging.getLogger(__name__)


class LoggedDecorator(InstrumentDecorator):
    """Wraps an Instrument to log all public method calls.

    Each call produces a structured log message at INFO level with
    the method name, arguments, and instrument composite key.
    """

    def quote(self) -> Any:
        """Fetch quote with logging."""
        logger.info("logged: quote() called for %s", self._wrapped.composite_key)
        return self._wrapped.quote()

    def ltp(self) -> Any:
        """Fetch LTP with logging."""
        logger.info("logged: ltp() called for %s", self._wrapped.composite_key)
        return self._wrapped.ltp()

    def depth(self, levels: int = 5) -> Any:
        """Fetch market depth with logging."""
        logger.info(
            "logged: depth(%d) called for %s",
            levels,
            self._wrapped.composite_key,
        )
        return self._wrapped.depth(levels)

    def ohlcv(self, *args: Any, **kwargs: Any) -> Any:
        """Fetch historical candles with logging."""
        logger.info(
            "logged: ohlcv() called for %s",
            self._wrapped.composite_key,
        )
        return self._wrapped.ohlcv(*args, **kwargs)

    def subscribe(self, *args: Any, **kwargs: Any) -> Any:
        """Subscribe to live ticks with logging."""
        logger.info(
            "logged: subscribe() called for %s",
            self._wrapped.composite_key,
        )
        return self._wrapped.subscribe(*args, **kwargs)

    def buy(self, quantity: int, **kwargs: Any) -> Any:
        """Place buy order with logging."""
        logger.info(
            "logged: buy(%d) called for %s",
            quantity,
            self._wrapped.composite_key,
        )
        return self._wrapped.buy(quantity, **kwargs)

    def sell(self, quantity: int, **kwargs: Any) -> Any:
        """Place sell order with logging."""
        logger.info(
            "logged: sell(%d) called for %s",
            quantity,
            self._wrapped.composite_key,
        )
        return self._wrapped.sell(quantity, **kwargs)

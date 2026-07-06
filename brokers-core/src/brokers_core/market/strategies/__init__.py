"""Option strategy library — multi-leg option strategies.

Strategies are composed of ``Instrument`` objects and support risk
calculation (max_profit, max_loss, break_even, PnL at spot) and
order placement via ``place_orders()``.

Available strategies:
    - ``VerticalSpread`` — 2-leg: bull call, bear call, bull put, bear put
    - ``Straddle`` — 2-leg: long/short same-strike call + put
    - ``Strangle`` — 2-leg: long/short OTM call + OTM put
    - ``IronCondor`` — 4-leg: short put/put/call/long call
    - ``ComboOrder`` — N-leg custom strategy builder

Usage::

    from brokers_core.market.strategies import VerticalSpread

    chain = inst.option_chain("2025-01-30")
    strikes = chain.nearest_strikes(5)

    spread = VerticalSpread(
        underlying=inst,
        long_leg=strikes[0].call.instrument,
        short_leg=strikes[4].call.instrument,
        quantity=25,
        side="bull_call",
    )

    spread.max_profit    # max profit
    spread.max_loss      # max loss
    spread.net_premium   # net premium paid/received
    spread.break_even    # break-even price(s)
    spread.pnl_at(spot)  # PnL at a given spot price
    spread.place_orders()  # executes all leg orders
"""

from brokers_core.market.strategies.base import OptionStrategy as OptionStrategy
from brokers_core.market.strategies.base import StrategyLeg as StrategyLeg
from brokers_core.market.strategies.combo import ComboOrder as ComboOrder
from brokers_core.market.strategies.iron_condor import IronCondor as IronCondor
from brokers_core.market.strategies.straddle import Straddle as Straddle
from brokers_core.market.strategies.strangle import Strangle as Strangle
from brokers_core.market.strategies.vertical import VerticalSpread as VerticalSpread

__all__ = [
    "OptionStrategy",
    "StrategyLeg",
    "VerticalSpread",
    "Straddle",
    "Strangle",
    "IronCondor",
    "ComboOrder",
]

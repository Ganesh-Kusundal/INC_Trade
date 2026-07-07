"""TradeX CLI — command-line interface for the broker SDK.

Usage:
    tradex status          Show account status, connection, capabilities
    tradex orders          List open orders
    tradex positions       List open positions
    tradex holdings        List holdings
    tradex funds           Show fund limits
    tradex quote RELIANCE  Get live quote
    tradex history RELIANCE --days 30    Get daily history
    tradex chain NIFTY --expiry 2025-03-27   Show option chain
    tradex help            Show all commands

Environment variables:
    DHAN_CLIENT_ID         Dhan broker client ID
    DHAN_ACCESS_TOKEN      Dhan broker access token

Run:
    python -m tradex.cli status
    python -m tradex.cli quote RELIANCE
    python -m tradex.cli history RELIANCE --days 30
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from decimal import Decimal


def _get_platform():
    """Create and return a BrokerPlatform connected to Dhan."""
    from tradex.platform import BrokerPlatform
    from tradex.providers.dhan.provider import DhanProvider

    client_id = os.environ.get("DHAN_CLIENT_ID", "")
    access_token = os.environ.get("DHAN_ACCESS_TOKEN", "")

    if not client_id or not access_token:
        print("ERROR: Set DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN env vars.")
        print("")
        print("  export DHAN_CLIENT_ID='your_client_id'")
        print("  export DHAN_ACCESS_TOKEN='your_access_token'")
        sys.exit(1)

    provider = DhanProvider(client_id=client_id, access_token=access_token)
    return BrokerPlatform(provider)


# ── Commands ─────────────────────────────────────────────────────────


async def cmd_status(args) -> None:
    """Show account status, connection, capabilities."""
    platform = _get_platform()

    try:
        await platform.connect()

        print("╔══════════════════════════════════════╗")
        print("║        TradeX Broker Status          ║")
        print("╚══════════════════════════════════════╝")
        print()

        # Connection
        print("  Connection:")
        print(f"    Provider:       {platform.provider_name}")
        print(f"    Connected:      {'Yes' if platform.is_connected else 'No'}")

        # Capabilities
        caps = platform.capabilities
        print(f"\n  Capabilities ({len(caps)}):")
        for cap in caps:
            print(f"    • {cap}")

        # Fund limits
        try:
            funds = await platform.get_fund_limits()
            print("\n  Fund Limits:")
            print(f"    Available:      ₹{funds.available_balance:>12,.2f}")
            print(f"    Utilized:       ₹{funds.utilized:>12,.2f}")
            print(f"    Net available:  ₹{funds.net_available:>12,.2f}")
        except Exception as e:
            print(f"\n  Fund limits unavailable: {e}")

        # Health
        try:
            health = await platform.health()
            print("\n  Health:")
            for comp in health.components:
                status_icon = "✓" if comp.status.value == "healthy" else "✗"
                print(f"    {status_icon} {comp.name}: {comp.message}")
        except Exception:
            pass

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
    finally:
        await platform.disconnect()


async def cmd_orders(args) -> None:
    """List open orders."""
    platform = _get_platform()

    try:
        await platform.connect()
        orders = await platform.get_orders()

        if not orders:
            print("No orders found.")
            return

        print(
            f"{'Order ID':<20} {'Symbol':<15} {'Side':<5} {'Type':<10} "
            f"{'Qty':>6} {'Price':>10} {'Status':<15}"
        )
        print("─" * 95)

        for o in orders:
            status_marker = "●" if o.is_active else "○"
            print(
                f"{o.order_id:<20} {o.trading_symbol:<15} {o.side.value:<5} "
                f"{o.order_type.value:<10} {o.quantity:>6} "
                f"₹{o.price:>9,.2f} {status_marker} {o.status.value}"
            )

        active = sum(1 for o in orders if o.is_active)
        print(f"\n  {len(orders)} orders total, {active} active")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
    finally:
        await platform.disconnect()


async def cmd_positions(args) -> None:
    """List open positions."""
    platform = _get_platform()

    try:
        await platform.connect()
        positions = await platform.get_positions()
        open_positions = [p for p in positions if p.is_open]

        if not open_positions:
            print("No open positions.")
            return

        print(
            f"{'Symbol':<15} {'Type':<6} {'Net Qty':>8} {'Buy Avg':>12} "
            f"{'Sell Avg':>12} {'P&L':>12}"
        )
        print("─" * 75)

        total_pnl = Decimal("0")
        for p in open_positions:
            pnl = p.realized_profit + p.unrealized_profit
            total_pnl += pnl
            pnl_marker = "+" if pnl >= 0 else ""
            print(
                f"{p.trading_symbol:<15} {p.position_type.value:<6} "
                f"{p.net_quantity:>8} ₹{p.buy_average:>10,.2f} "
                f"₹{p.sell_average:>10,.2f} {pnl_marker}₹{pnl:>9,.2f}"
            )

        print("─" * 75)
        marker = "+" if total_pnl >= 0 else ""
        print(f"{'Total P&L':>54} {marker}₹{total_pnl:>9,.2f}")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
    finally:
        await platform.disconnect()


async def cmd_holdings(args) -> None:
    """List holdings."""
    platform = _get_platform()

    try:
        await platform.connect()
        holdings = await platform.get_holdings()

        if not holdings:
            print("No holdings found.")
            return

        print(
            f"{'Symbol':<15} {'ISIN':<14} {'Qty':>6} {'DP Qty':>7} "
            f"{'T1 Qty':>7} {'Avg Cost':>12} {'Value':>14}"
        )
        print("─" * 85)

        total_value = Decimal("0")
        for h in holdings:
            value = h.average_cost_price * h.total_quantity
            total_value += value
            print(
                f"{h.trading_symbol:<15} {h.isin:<14} {h.total_quantity:>6} "
                f"{h.dp_quantity:>7} {h.t1_quantity:>7} "
                f"₹{h.average_cost_price:>10,.2f} ₹{value:>12,.2f}"
            )

        print("─" * 85)
        print(f"{'Total':>51} {'':>7} {'':>7} {'':>12} ₹{total_value:>12,.2f}")
        print(f"\n  {len(holdings)} holdings")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
    finally:
        await platform.disconnect()


async def cmd_funds(args) -> None:
    """Show fund limits."""
    platform = _get_platform()

    try:
        await platform.connect()
        funds = await platform.get_fund_limits()

        print("╔══════════════════════════════════════╗")
        print("║           Fund Limits                ║")
        print("╚══════════════════════════════════════╝")
        print()
        print(f"  Available balance:   ₹{funds.available_balance:>12,.2f}")
        print(f"  SOD limit:           ₹{funds.sod_limit:>12,.2f}")
        print(f"  Collateral:          ₹{funds.collateral:>12,.2f}")
        print(f"  Receivable:          ₹{funds.receivable:>12,.2f}")
        print(f"  Utilized:            ₹{funds.utilized:>12,.2f}")
        print(f"  Blocked payout:      ₹{funds.blocked_payout:>12,.2f}")
        print(f"  Withdrawable:        ₹{funds.withdrawable:>12,.2f}")
        print()
        print("  ─────────────────────────────────────")
        print(f"  Net available:       ₹{funds.net_available:>12,.2f}")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
    finally:
        await platform.disconnect()


async def cmd_quote(args) -> None:
    """Get live quote for a symbol."""
    platform = _get_platform()

    try:
        await platform.connect()

        symbol = args.symbol.upper()
        instrument = await platform.resolve_instrument(symbol)
        if not instrument:
            print(f"ERROR: Could not resolve '{symbol}'.")
            return

        quote = await platform.get_quote(instrument)

        print("╔══════════════════════════════════════╗")
        print(f"║  Quote: {instrument.trading_symbol:<28}  ║")
        print("╚══════════════════════════════════════╝")
        print()
        print(f"  Last price:   ₹{quote.last_price:>12,.2f}")
        print(f"  Open:         ₹{quote.open:>12,.2f}")
        print(f"  High:         ₹{quote.high:>12,.2f}")
        print(f"  Low:          ₹{quote.low:>12,.2f}")
        print(f"  Close:        ₹{quote.close:>12,.2f}")
        print(f"  Volume:       {quote.volume:>12,}")
        print(f"  Bid:          ₹{quote.bid_price:>10,.2f} x {quote.bid_quantity}")
        print(f"  Ask:          ₹{quote.ask_price:>10,.2f} x {quote.ask_quantity}")
        print(f"  Change:       {quote.change_pct:>+11.2f}%")
        if quote.upper_circuit > 0:
            print(f"  Upper circuit: ₹{quote.upper_circuit:>11,.2f}")
            print(f"  Lower circuit: ₹{quote.lower_circuit:>11,.2f}")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
    finally:
        await platform.disconnect()


async def cmd_history(args) -> None:
    """Get daily OHLCV history."""
    platform = _get_platform()

    try:
        await platform.connect()

        symbol = args.symbol.upper()
        days = args.days
        instrument = await platform.resolve_instrument(symbol)
        if not instrument:
            print(f"ERROR: Could not resolve '{symbol}'.")
            return

        end = date.today()
        start = end - timedelta(days=days)

        print(f"Fetching {days} days of daily data for {instrument.trading_symbol}...")
        data = await platform.get_history(
            instrument=instrument,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
        )

        if not data:
            print("No data returned.")
            return

        print(f"\n{'Date':<12} {'Open':>10} {'High':>10} {'Low':>10} {'Close':>10} {'Volume':>12}")
        print("─" * 72)

        for c in data:
            ts = c.timestamp.strftime("%Y-%m-%d")
            print(
                f"{ts:<12} ₹{c.open:>8,.2f} ₹{c.high:>8,.2f} "
                f"₹{c.low:>8,.2f} ₹{c.close:>8,.2f} {c.volume:>12,}"
            )

        print("─" * 72)
        prices = [c.close for c in data]
        print(f"  {len(data)} candles | Range: ₹{min(prices):,.2f} – ₹{max(prices):,.2f}")
        if len(prices) > 1:
            ret = (prices[-1] - prices[0]) / prices[0] * 100
            print(f"  Period return: {ret:+.2f}%")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
    finally:
        await platform.disconnect()


async def cmd_chain(args) -> None:
    """Show option chain."""
    platform = _get_platform()

    try:
        await platform.connect()

        from tradex.domain.instruments import BUILTIN_INSTRUMENTS

        symbol = args.symbol.upper()
        if symbol in BUILTIN_INSTRUMENTS:
            underlying = BUILTIN_INSTRUMENTS[symbol]
        else:
            underlying = await platform.resolve_instrument(symbol)
            if not underlying:
                print(f"ERROR: Could not resolve '{symbol}'.")
                return

        print(f"Underlying: {underlying} (Spot: loading...)")

        # Get expiry list
        expiry_list = await platform.get_expiry_list(underlying)
        if not expiry_list:
            print("No expiry dates available.")
            return

        # Use specified expiry or nearest
        if args.expiry:
            expiry = args.expiry
            if expiry not in expiry_list:
                print(f"Expiry {expiry} not available.")
                print(f"Available: {', '.join(expiry_list[:5])}...")
                return
        else:
            expiry = expiry_list[0]
            print(f"Using nearest expiry: {expiry}")

        chain = await platform.get_option_chain(underlying, expiry)

        print(f"\n  Spot: ₹{chain.spot_price} | Expiry: {expiry}")
        print(f"  PCR: {chain.pcr:.4f} | Strikes: {len(chain.strikes)}")

        atm = chain.find_atm()

        print(f"\n{'Strike':>10}  {'CE LTP':>10} {'CE OI':>12}  │  {'PE LTP':>10} {'PE OI':>12}")
        print(f"{'─' * 10}  {'─' * 10} {'─' * 12}  │  {'─' * 10} {'─' * 12}")

        for strike in chain.strikes:
            ce_ltp = f"₹{strike.call.last_price:>8,.2f}" if strike.call else " " * 10
            ce_oi = f"{strike.call.open_interest:>12,}" if strike.call else " " * 12
            pe_ltp = f"₹{strike.put.last_price:>8,.2f}" if strike.put else " " * 10
            pe_oi = f"{strike.put.open_interest:>12,}" if strike.put else " " * 12

            marker = " ◄ ATM" if atm and strike.strike == atm.strike else ""
            print(f"{strike.strike:>10}  {ce_ltp} {ce_oi}  │  {pe_ltp} {pe_oi}{marker}")

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
    finally:
        await platform.disconnect()


async def cmd_help(args) -> None:
    """Show all commands."""
    print("TradeX CLI — Broker SDK Command Line Interface")
    print()
    print("Usage: tradex <command> [arguments]")
    print()
    print("Commands:")
    print("  status                          Show account status and capabilities")
    print("  orders                          List all orders")
    print("  positions                       List open positions")
    print("  holdings                        List portfolio holdings")
    print("  funds                           Show fund limits")
    print("  quote <SYMBOL>                  Get live quote")
    print("  history <SYMBOL> --days N       Get daily OHLCV history")
    print("  chain <SYMBOL> --expiry DATE    Show option chain")
    print("  help                            Show this help")
    print()
    print("Environment Variables:")
    print("  DHAN_CLIENT_ID                  Dhan broker client ID")
    print("  DHAN_ACCESS_TOKEN               Dhan broker access token")
    print()
    print("Examples:")
    print("  tradex status")
    print("  tradex quote RELIANCE")
    print("  tradex history TCS --days 30")
    print("  tradex chain NIFTY --expiry 2025-03-27")


# ── Argument parser ──────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="tradex",
        description="TradeX Broker SDK — command-line trading interface",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # status
    subparsers.add_parser("status", help="Show account status and capabilities")

    # orders
    subparsers.add_parser("orders", help="List all orders")

    # positions
    subparsers.add_parser("positions", help="List open positions")

    # holdings
    subparsers.add_parser("holdings", help="List portfolio holdings")

    # funds
    subparsers.add_parser("funds", help="Show fund limits")

    # quote
    quote_parser = subparsers.add_parser("quote", help="Get live quote")
    quote_parser.add_argument("symbol", help="Trading symbol (e.g., RELIANCE)")

    # history
    history_parser = subparsers.add_parser("history", help="Get daily OHLCV history")
    history_parser.add_argument("symbol", help="Trading symbol (e.g., RELIANCE)")
    history_parser.add_argument("--days", type=int, default=30, help="Number of days (default: 30)")

    # chain
    chain_parser = subparsers.add_parser("chain", help="Show option chain")
    chain_parser.add_argument("symbol", help="Underlying symbol (e.g., NIFTY)")
    chain_parser.add_argument(
        "--expiry", type=str, default="", help="Expiry date (e.g., 2025-03-27)"
    )

    # help
    subparsers.add_parser("help", help="Show all commands")

    return parser


# ── Main ─────────────────────────────────────────────────────────────

COMMANDS = {
    "status": cmd_status,
    "orders": cmd_orders,
    "positions": cmd_positions,
    "holdings": cmd_holdings,
    "funds": cmd_funds,
    "quote": cmd_quote,
    "history": cmd_history,
    "chain": cmd_chain,
    "help": cmd_help,
}


def main() -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        cmd_help(args)
        return

    handler = COMMANDS.get(args.command)
    if handler:
        asyncio.run(handler(args))
    else:
        print(f"Unknown command: {args.command}")
        cmd_help(args)


if __name__ == "__main__":
    main()

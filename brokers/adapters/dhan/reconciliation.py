"""Dhan Reconciliation adapter."""

from __future__ import annotations

import logging

from brokers.adapters.dhan.portfolio import DhanPortfolio

logger = logging.getLogger(__name__)


class DhanReconciliation:
    """Reconciliation adapter for Dhan to match local and remote positions."""

    def __init__(self, portfolio: DhanPortfolio) -> None:
        self._portfolio = portfolio

    def reconcile_positions(self, local_positions: list[dict]) -> dict:
        """Reconcile local positions against broker positions.

        Returns a dict indicating matches, missing remote, missing local, and mismatched quantities.
        """
        logger.info("running_position_reconciliation")
        try:
            remote_positions = self._portfolio.positions()
        except Exception as e:
            logger.error(f"Failed to fetch remote positions for reconciliation: {e}")
            return {"error": str(e)}

        local_map = {p.get("symbol"): p for p in local_positions if p.get("symbol")}
        remote_map = {p.symbol: p for p in remote_positions}

        all_symbols = set(local_map.keys()) | set(remote_map.keys())

        matched = []
        missing_local = []
        missing_remote = []
        mismatched_qty = []

        for symbol in all_symbols:
            local_p = local_map.get(symbol)
            remote_p = remote_map.get(symbol)

            if local_p and not remote_p:
                if local_p.get("quantity", 0) != 0:
                    missing_remote.append(symbol)
            elif remote_p and not local_p:
                if remote_p.quantity != 0:
                    missing_local.append(symbol)
            else:
                l_qty = local_p.get("quantity", 0)
                r_qty = remote_p.quantity

                if l_qty == r_qty:
                    matched.append(symbol)
                else:
                    mismatched_qty.append(
                        {"symbol": symbol, "local_qty": l_qty, "remote_qty": r_qty}
                    )

        return {
            "matched": matched,
            "missing_local": missing_local,
            "missing_remote": missing_remote,
            "mismatched_qty": mismatched_qty,
        }

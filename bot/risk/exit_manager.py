"""Exit management: re-price open positions and close on TP / SL / expiry."""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

from ..broker.paper_broker import PaperBroker
from ..models import Position

logger = logging.getLogger(__name__)


def current_cost_to_close(pos: Position, chain_df: pd.DataFrame) -> float:
    """
    Estimate the cost to close a position using the live chain.
    Cost to close = pay for short legs, receive for long legs (returned as net cost).
    """
    cost = 0.0
    for leg in pos.strategy.legs:
        match = chain_df[
            (chain_df["optionType"] == leg.option_type)
            & (chain_df["expiration"] == leg.expiration)
            & (abs(chain_df["strike"] - leg.strike) < 0.001)
        ]
        if match.empty:
            px = leg.premium  # stale fallback
        else:
            row = match.iloc[0]
            mid = float(row.get("mid_price", 0.0) or 0.0)
            px = mid if mid > 0 else float(row.get("lastPrice", 0.0) or leg.premium)
        if leg.action == "sell":
            cost += px * leg.qty * 100   # buy back
        else:
            cost -= px * leg.qty * 100   # sell to close
    return cost


def manage_exits(broker: PaperBroker, chain_df: pd.DataFrame, cfg: dict) -> list[str]:
    """Close open positions that hit profit target, stop loss, or expiry. Returns close reasons."""
    actions: list[str] = []
    tp = float(cfg.get("profit_target_pct", 0.50))
    sl = float(cfg.get("stop_loss_pct", 2.00))
    exit_days = int(cfg.get("exit_days_before_expiry", 2))

    for pos in list(broker.account.open_positions):
        cost = current_cost_to_close(pos, chain_df)
        credit = pos.entry_credit
        pnl_if_closed = credit - cost

        reason = None
        # Profit target: captured >= tp fraction of credit (cost to close shrinks)
        if credit > 0 and pnl_if_closed >= credit * tp:
            reason = f"profit_target (captured ${pnl_if_closed:.2f} of ${credit:.2f})"
        # Stop loss: cost to close exceeds credit + sl*credit
        elif credit > 0 and cost >= credit * (1 + sl):
            reason = f"stop_loss (cost ${cost:.2f} vs credit ${credit:.2f})"
        else:
            # Expiry: close if the earliest leg is within exit_days
            try:
                exps = [datetime.strptime(l.expiration, "%Y-%m-%d") for l in pos.strategy.legs]
                dte = (min(exps) - datetime.now()).days
                if dte <= exit_days:
                    reason = f"approaching_expiry (dte={dte})"
            except ValueError:
                pass

        if reason:
            broker.close_position(pos, cost, reason)
            actions.append(f"{pos.ticker} {pos.id}: {reason}")
    return actions

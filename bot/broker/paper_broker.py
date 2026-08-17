"""Paper broker: simulated fills, persistent portfolio state, P&L.

State lives in state/paper_portfolio.json. Fills use the leg mid price with a
conservative slippage haircut on credits.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict
from datetime import datetime

from ..models import Account, Position, Strategy

logger = logging.getLogger(__name__)

STATE_DIR = os.path.join(os.getcwd(), "state")
STATE_FILE = os.path.join(STATE_DIR, "paper_portfolio.json")


class PaperBroker:
    def __init__(self, starting_capital: float = 100_000.0, slippage: float = 0.02):
        self.starting_capital = starting_capital
        self.slippage = slippage  # 2% adverse slippage on the net credit
        self.account = self._load() or Account(cash=starting_capital)

    # ---------------- persistence ----------------
    def _load(self) -> Account | None:
        if not os.path.exists(STATE_FILE):
            return None
        try:
            with open(STATE_FILE) as f:
                raw = json.load(f)
            acct = Account(cash=raw["cash"], realized_pnl_total=raw.get("realized_pnl_total", 0.0))
            for p in raw.get("positions", []):
                strat = p["strategy"]
                s = Strategy(
                    name=strat["name"], type=strat["type"], ticker=strat["ticker"],
                    bias=strat["bias"], legs=[], metrics=strat.get("metrics", {}),
                )
                from ..models import Leg
                for l in strat["legs"]:
                    s.legs.append(Leg(**l))
                acct.positions.append(Position(
                    id=p["id"], strategy=s, opened_at=p["opened_at"],
                    entry_credit=p["entry_credit"], status=p["status"],
                    closed_at=p.get("closed_at"), close_reason=p.get("close_reason"),
                    realized_pnl=p.get("realized_pnl"),
                ))
            return acct
        except Exception as e:
            logger.error("failed to load state (%s) — starting fresh", e)
            return None

    def save(self):
        os.makedirs(STATE_DIR, exist_ok=True)
        raw = {
            "cash": self.account.cash,
            "realized_pnl_total": self.account.realized_pnl_total,
            "positions": [asdict(p) for p in self.account.positions],
        }
        with open(STATE_FILE, "w") as f:
            json.dump(raw, f, indent=2)

    def reset(self):
        self.account = Account(cash=self.starting_capital)
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        logger.info("paper account reset to $%.2f", self.starting_capital)

    # ---------------- trading ----------------
    def open_position(self, strategy: Strategy) -> Position:
        """Fill a strategy at mid with slippage; debit/credit cash accordingly."""
        credit = strategy.net_premium
        # adverse slippage: receive less credit on entry
        filled_credit = credit * (1 - self.slippage)
        self.account.cash += filled_credit  # credit received (positive for spreads)

        pos = Position(
            id=str(uuid.uuid4())[:8],
            strategy=strategy,
            opened_at=datetime.now().isoformat(timespec="seconds"),
            entry_credit=round(filled_credit, 2),
        )
        self.account.positions.append(pos)
        self.save()
        logger.info("OPENED %s %s id=%s credit=$%.2f", strategy.ticker, strategy.name,
                    pos.id, filled_credit)
        return pos

    def close_position(self, pos: Position, current_cost: float, reason: str):
        """
        Close at current market cost (what we'd pay to buy back / sell the legs now).
        P&L = entry credit received - cost to exit - slippage.
        """
        exit_cost = current_cost * (1 + self.slippage)
        pnl = pos.entry_credit - exit_cost
        pos.status = "closed"
        pos.closed_at = datetime.now().isoformat(timespec="seconds")
        pos.close_reason = reason
        pos.realized_pnl = round(pnl, 2)
        self.account.cash -= exit_cost
        self.account.realized_pnl_total += pnl
        self.save()
        logger.info("CLOSED %s id=%s reason=%s pnl=$%.2f", pos.ticker, pos.id, reason, pnl)
        return pnl

    # ---------------- valuation ----------------
    @staticmethod
    def mark_position(pos: Position, chain_lookup) -> float:
        """
        Estimate current cost-to-close for an open position using chain_lookup
        (function leg -> current mid price). Returns cost in dollars.
        """
        cost = 0.0
        for leg in pos.strategy.legs:
            px = chain_lookup(leg)
            # to close: we bought -> sell (receive), we sold -> buy back (pay)
            if leg.action == "sell":
                cost += px * leg.qty * 100
            else:
                cost -= px * leg.qty * 100
        return cost

    def summary(self) -> dict:
        open_pos = self.account.open_positions
        return {
            "cash": round(self.account.cash, 2),
            "open_positions": len(open_pos),
            "realized_pnl": round(self.account.realized_pnl_total, 2),
            "positions": [
                {"id": p.id, "ticker": p.ticker, "name": p.strategy.name,
                 "opened": p.opened_at, "credit": p.entry_credit, "status": p.status,
                 "pnl": p.realized_pnl, "reason": p.close_reason}
                for p in self.account.positions[-20:]
            ],
        }

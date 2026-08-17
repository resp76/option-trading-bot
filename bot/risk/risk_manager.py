"""Risk management: gates every candidate before it reaches the broker."""
from __future__ import annotations

import logging
from datetime import datetime

from ..models import Account, Strategy

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, cfg: dict):
        self.cfg = cfg

    def check(self, strategy: Strategy, account: Account, spot: float) -> tuple[bool, str]:
        """Return (approved, reason)."""
        cfg = self.cfg

        # --- position caps ---
        if len(account.open_positions) >= int(cfg.get("max_open_positions", 4)):
            return False, "max open positions reached"
        same_ticker = [p for p in account.open_positions if p.ticker == strategy.ticker]
        if len(same_ticker) >= int(cfg.get("max_positions_per_ticker", 1)):
            return False, f"already have {len(same_ticker)} position(s) in {strategy.ticker}"

        # --- structure type ---
        undefined_risk = any(l.action == "sell" for l in strategy.legs) and not any(
            l.action == "buy" for l in strategy.legs)
        if undefined_risk and not cfg.get("allow_undefined_risk", False):
            return False, "undefined-risk structure blocked by config"

        # --- credit / sizing ---
        credit = strategy.net_premium
        min_credit = float(cfg.get("min_credit", 0.5)) * 100  # per-contract dollars
        if credit < min_credit:
            return False, f"credit ${credit:.2f} below minimum ${min_credit:.2f}"

        margin_req = strategy.metrics.get("margin_req", 0.0)
        max_capital = float(cfg.get("max_capital_per_trade", 5000))
        if margin_req > max_capital:
            return False, f"margin ${margin_req:.0f} exceeds per-trade cap ${max_capital:.0f}"
        if margin_req > account.cash:
            return False, "insufficient paper cash"

        # --- liquidity per leg ---
        min_vol = int(cfg.get("min_volume", 10))
        min_oi = int(cfg.get("min_open_interest", 50))
        for leg in strategy.legs:
            if leg.volume < min_vol:
                return False, f"leg {leg.option_type} {leg.strike}: volume {leg.volume} < {min_vol}"
            if leg.open_interest < min_oi:
                return False, f"leg {leg.option_type} {leg.strike}: OI {leg.open_interest} < {min_oi}"

        # --- expiry window sanity ---
        min_dte = int(cfg.get("min_dte", 20))
        for leg in strategy.legs:
            try:
                dte = (datetime.strptime(leg.expiration, "%Y-%m-%d") - datetime.now()).days
            except ValueError:
                return False, f"bad expiration {leg.expiration}"
            if dte < min_dte:
                return False, f"leg expiry {leg.expiration} closer than min_dte"

        return True, "approved"

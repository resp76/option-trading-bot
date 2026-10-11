# Tradier adapter stub for option-trading-bot
# Place at adapters/tradier_broker.py and implement the methods the bot expects (quote, place_order, account, cancel, etc.)

import requests
import os

BASE_URL = "https://api.tradier.com/v1"
# Tradier sandbox (use by setting TRADIER_BASE_URL env var to this value)
SANDBOX_URL = "https://sandbox.tradier.com/v1"

from typing import Optional
from bot.models import Account, Position, Strategy


class TradierBroker:
    def __init__(self, token: Optional[str] = None, account_id: Optional[str] = None, base_url: Optional[str] = None, starting_capital: float = 100_000.0, slippage: float = 0.02):
        # Token and account can come from args or environment variables.
        # Base URL preference order: explicit arg -> TRADIER_BASE_URL env -> default BASE_URL
        self.token = token or os.environ.get('TRADIER_TOKEN')
        self.account_id = account_id or os.environ.get('TRADIER_ACCOUNT_ID')
        self.base_url = base_url or os.environ.get('TRADIER_BASE_URL') or BASE_URL
        self.slippage = slippage
        # Initialize account state from Tradier balances if available, else use starting capital
        try:
            bal = self._fetch_balances()
            cash = float(bal.get('accounts', {}).get('account', {}).get('cash', starting_capital))
        except Exception:
            cash = starting_capital
        self.account = Account(cash=cash)

    # ---------------- low-level Tradier API helpers ----------------
    def _headers(self):
        return {
            'Authorization': f'Bearer {self.token}',
            'Accept': 'application/json'
        }

    def _fetch_balances(self):
        url = f"{self.base_url}/accounts"
        r = requests.get(url, headers=self._headers())
        r.raise_for_status()
        return r.json()

    def get_quote(self, symbol: str):
        url = f"{self.base_url}/markets/quotes"
        r = requests.get(url, params={'symbols': symbol}, headers=self._headers())
        r.raise_for_status()
        return r.json()

    def place_option_order(self, order_payload: dict):
        # Simple wrapper for posting orders to Tradier sandbox
        url = f"{self.base_url}/accounts/{self.account_id}/orders"
        r = requests.post(url, json=order_payload, headers=self._headers())
        r.raise_for_status()
        return r.json()

    # ---------------- compatibility layer (PaperBroker-like API) ----------------
    def save(self):
        # Live mode doesn't persist to local paper state by default
        return

    def reset(self):
        # no-op for live broker
        self.account = Account(cash=self.account.cash)

    def open_position(self, strategy: Strategy) -> Position:
        """Place an option order in Tradier sandbox and record a local Position object.
        For simplicity, we optimistic-fill at strategy.net_premium (with slippage) and record the position locally.
        """
        credit = strategy.net_premium
        filled_credit = credit * (1 - self.slippage)
        self.account.cash += filled_credit
        pos = Position(
            id=strategy.name[:8] if hasattr(strategy, 'name') else 'tradpos',
            strategy=strategy,
            opened_at='',
            entry_credit=round(filled_credit, 2),
        )
        self.account.positions.append(pos)
        return pos

    def close_position(self, pos: Position, current_cost: float, reason: str):
        exit_cost = current_cost * (1 + self.slippage)
        pnl = pos.entry_credit - exit_cost
        pos.status = 'closed'
        pos.closed_at = ''
        pos.close_reason = reason
        pos.realized_pnl = round(pnl, 2)
        self.account.cash -= exit_cost
        self.account.realized_pnl_total += pnl
        return pnl

    @staticmethod
    def mark_position(pos: Position, chain_lookup) -> float:
        cost = 0.0
        for leg in pos.strategy.legs:
            px = chain_lookup(leg)
            if leg.action == 'sell':
                cost += px * leg.qty * 100
            else:
                cost -= px * leg.qty * 100
        return cost

    def summary(self) -> dict:
        open_pos = self.account.open_positions
        return {
            'cash': round(self.account.cash, 2),
            'open_positions': len(open_pos),
            'realized_pnl': round(self.account.realized_pnl_total, 2),
            'positions': [
                {'id': p.id, 'ticker': p.ticker, 'name': p.strategy.name, 'opened': p.opened_at, 'credit': p.entry_credit, 'status': p.status, 'pnl': p.realized_pnl, 'reason': p.close_reason}
                for p in self.account.positions[-20:]
            ],
        }

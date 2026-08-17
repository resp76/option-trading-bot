"""Shared data models."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

LegAction = Literal["buy", "sell"]
OptionType = Literal["call", "put"]
Bias = Literal["bullish", "bearish", "neutral"]


@dataclass
class Leg:
    """One option leg of a strategy."""
    ticker: str
    option_type: OptionType
    strike: float
    expiration: str          # YYYY-MM-DD
    action: LegAction
    qty: int = 1
    premium: float = 0.0     # per-share price used for fill
    iv: Optional[float] = None
    delta: Optional[float] = None
    bid: float = 0.0
    ask: float = 0.0
    volume: int = 0
    open_interest: int = 0

    def mid(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return (self.bid + self.ask) / 2.0
        return self.premium


@dataclass
class Strategy:
    """A candidate or live strategy with legs and metrics."""
    name: str
    type: str                # bull_put_spread | bear_call_spread | iron_condor | short_strangle
    ticker: str
    bias: Bias
    legs: list[Leg] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def net_premium(self) -> float:
        """Net credit in dollars for the whole position (positive = credit received)."""
        total = 0.0
        for leg in self.legs:
            cost = leg.premium * leg.qty * 100
            total += cost if leg.action == "sell" else -cost
        return total

    def max_loss(self) -> float:
        ml = self.metrics.get("max_loss")
        if isinstance(ml, (int, float)):
            return float(ml)
        return float("inf")


@dataclass
class Position:
    """An open paper position."""
    id: str
    strategy: Strategy
    opened_at: str
    entry_credit: float          # net credit received ($)
    status: str = "open"         # open | closed
    closed_at: Optional[str] = None
    close_reason: Optional[str] = None
    realized_pnl: Optional[float] = None

    @property
    def ticker(self) -> str:
        return self.strategy.ticker


@dataclass
class Account:
    """Paper account state."""
    cash: float
    positions: list[Position] = field(default_factory=list)
    realized_pnl_total: float = 0.0

    @property
    def open_positions(self) -> list[Position]:
        return [p for p in self.positions if p.status == "open"]

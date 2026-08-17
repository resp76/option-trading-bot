"""Tests for the paper broker and risk manager."""
import os

import pandas as pd
import pytest

from bot.broker.paper_broker import PaperBroker
from bot.models import Account, Leg, Strategy
from bot.risk.risk_manager import RiskManager

CFG = {
    "starting_capital": 100_000,
    "max_open_positions": 2,
    "max_positions_per_ticker": 1,
    "max_capital_per_trade": 5000,
    "min_credit": 0.50,
    "min_volume": 10,
    "min_open_interest": 50,
    "min_dte": 20,
    "allow_undefined_risk": False,
}


def make_leg(action, strike, otype="put", vol=100, oi=500, premium=1.0):
    return Leg(ticker="TEST", option_type=otype, strike=strike,
               expiration="2099-01-15", action=action, qty=1,
               premium=premium, volume=vol, open_interest=oi)


def make_spread() -> Strategy:
    s = Strategy(name="Bull Put Spread", type="bull_put_spread",
                 ticker="TEST", bias="bullish",
                 legs=[make_leg("sell", 95, premium=2.0),
                       make_leg("buy", 90, premium=0.5)])
    s.metrics = {"net_premium": 150.0, "max_loss": 350.0,
                 "margin_req": 350.0, "roc_percent": 42.9}
    return s


def test_open_position_credits_cash(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.broker.paper_broker.STATE_DIR", str(tmp_path))
    monkeypatch.setattr("bot.broker.paper_broker.STATE_FILE",
                        os.path.join(str(tmp_path), "paper_portfolio.json"))
    broker = PaperBroker(starting_capital=100_000)
    strat = make_spread()
    pos = broker.open_position(strat)
    # credit = (2.0-0.5)*100 = 150, minus 2% slippage = 147
    assert broker.account.cash == pytest.approx(100_147.0)
    assert pos.entry_credit == pytest.approx(147.0)
    assert len(broker.account.open_positions) == 1


def test_close_position_realizes_pnl(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.broker.paper_broker.STATE_DIR", str(tmp_path))
    monkeypatch.setattr("bot.broker.paper_broker.STATE_FILE",
                        os.path.join(str(tmp_path), "paper_portfolio.json"))
    broker = PaperBroker(starting_capital=100_000)
    pos = broker.open_position(make_spread())
    # cost to close drops to 50 -> profit
    pnl = broker.close_position(pos, current_cost=50.0, reason="profit_target")
    # exit cost with slippage: 50*1.02 = 51; pnl = 147 - 51 = 96
    assert pnl == pytest.approx(96.0)
    assert pos.status == "closed"
    assert len(broker.account.open_positions) == 0


def test_state_persistence_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.broker.paper_broker.STATE_DIR", str(tmp_path))
    monkeypatch.setattr("bot.broker.paper_broker.STATE_FILE",
                        os.path.join(str(tmp_path), "paper_portfolio.json"))
    b1 = PaperBroker(starting_capital=100_000)
    b1.open_position(make_spread())
    b2 = PaperBroker(starting_capital=100_000)  # reload from disk
    assert len(b2.account.open_positions) == 1
    assert b2.account.cash == pytest.approx(b1.account.cash)


def test_risk_blocks_second_same_ticker():
    rm = RiskManager(CFG)
    acct = Account(cash=100_000)
    from bot.models import Position
    s = make_spread()
    acct.positions.append(Position(id="x", strategy=s, opened_at="now", entry_credit=147.0))
    ok, reason = rm.check(make_spread(), acct, spot=100.0)
    assert not ok
    assert "position" in reason.lower()


def test_risk_blocks_low_credit():
    rm = RiskManager(CFG)
    acct = Account(cash=100_000)
    s = make_spread()
    s.legs[0].premium = 0.52  # credit = (0.52-0.5)*100 = $2 < $50 min
    s.metrics["net_premium"] = 2.0
    ok, reason = rm.check(s, acct, spot=100.0)
    assert not ok
    assert "credit" in reason.lower()


def test_risk_blocks_illiquid():
    rm = RiskManager(CFG)
    acct = Account(cash=100_000)
    s = make_spread()
    s.legs[0].volume = 1
    ok, reason = rm.check(s, acct, spot=100.0)
    assert not ok
    assert "volume" in reason.lower()


def test_risk_approves_good_spread():
    rm = RiskManager(CFG)
    acct = Account(cash=100_000)
    ok, reason = rm.check(make_spread(), acct, spot=100.0)
    assert ok, reason

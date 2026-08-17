"""Tests for exit management."""
import os

import pandas as pd
import pytest

from bot.broker.paper_broker import PaperBroker
from bot.models import Leg, Strategy
from bot.risk.exit_manager import current_cost_to_close, manage_exits


def make_spread(premium_short=2.0, premium_long=0.5):
    s = Strategy(name="Bull Put Spread", type="bull_put_spread",
                 ticker="TEST", bias="bullish",
                 legs=[Leg(ticker="TEST", option_type="put", strike=95,
                           expiration="2099-01-15", action="sell", premium=premium_short),
                       Leg(ticker="TEST", option_type="put", strike=90,
                           expiration="2099-01-15", action="buy", premium=premium_long)])
    s.metrics = {"net_premium": 150.0, "max_loss": 350.0,
                 "margin_req": 350.0, "roc_percent": 42.9}
    return s


def chain_with_prices(short_px: float, long_px: float) -> pd.DataFrame:
    return pd.DataFrame([
        {"optionType": "put", "expiration": "2099-01-15", "strike": 95.0,
         "mid_price": short_px, "lastPrice": short_px},
        {"optionType": "put", "expiration": "2099-01-15", "strike": 90.0,
         "mid_price": long_px, "lastPrice": long_px},
    ])


def test_cost_to_close_math():
    s = make_spread()
    # cost to close = buy back short (pay 1.0) - sell long (receive 0.2) = 0.8*100 = 80
    cost = current_cost_to_close(
        type("P", (), {"strategy": s})(),
        chain_with_prices(short_px=1.0, long_px=0.2),
    )
    assert cost == pytest.approx(80.0)


def test_profit_target_triggers(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.broker.paper_broker.STATE_DIR", str(tmp_path))
    monkeypatch.setattr("bot.broker.paper_broker.STATE_FILE",
                        os.path.join(str(tmp_path), "p.json"))
    broker = PaperBroker(starting_capital=100_000)
    broker.open_position(make_spread())
    # credit received ~147; cost to close 80 -> captured 67 < 50% of 147? 67 >= 73.5? No.
    # make cost tiny: 0.1 -> captured ~137 >= 73.5 -> profit target
    chain = chain_with_prices(short_px=0.05, long_px=0.0)
    cfg = {"profit_target_pct": 0.50, "stop_loss_pct": 2.0, "exit_days_before_expiry": 2}
    actions = manage_exits(broker, chain, cfg)
    assert len(actions) == 1
    assert "profit_target" in actions[0]


def test_stop_loss_triggers(tmp_path, monkeypatch):
    monkeypatch.setattr("bot.broker.paper_broker.STATE_DIR", str(tmp_path))
    monkeypatch.setattr("bot.broker.paper_broker.STATE_FILE",
                        os.path.join(str(tmp_path), "p.json"))
    broker = PaperBroker(starting_capital=100_000)
    broker.open_position(make_spread())
    # cost to close explodes: short 6.0, long 0 -> cost 600 >= 147*(1+2)=441 -> SL
    chain = chain_with_prices(short_px=6.0, long_px=0.0)
    cfg = {"profit_target_pct": 0.50, "stop_loss_pct": 2.0, "exit_days_before_expiry": 2}
    actions = manage_exits(broker, chain, cfg)
    assert len(actions) == 1
    assert "stop_loss" in actions[0]

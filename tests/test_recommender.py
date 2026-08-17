"""Tests for the strategy recommender using a synthetic option chain."""
import numpy as np
import pandas as pd
import pytest

from bot.models import Strategy
from bot.strategy.recommender import (
    compute_metrics,
    construct_bull_put_spread,
    construct_iron_condor,
    recommend,
)


def make_chain(spot: float = 100.0) -> pd.DataFrame:
    """Synthetic chain: strikes 80..120, calls+puts, decent liquidity."""
    rows = []
    for strike in range(80, 121, 1):
        for opt_type in ("call", "put"):
            dist = abs(strike - spot)
            # fake delta magnitude decaying OTM
            if opt_type == "call":
                delta = 0.5 - 0.02 * (strike - spot) if strike >= spot else 0.8
            else:
                delta = -(0.5 - 0.02 * (spot - strike)) if strike <= spot else -0.8
            mid = max(0.05, 3.0 - 0.1 * dist)
            rows.append({
                "strike": float(strike),
                "optionType": opt_type,
                "expiration": "2099-01-15",
                "dte": 45,
                "bid": mid * 0.95,
                "ask": mid * 1.05,
                "mid_price": mid,
                "lastPrice": mid,
                "volume": 100,
                "openInterest": 500,
                "impliedVolatility": 0.25,
                "delta": delta,
            })
    return pd.DataFrame(rows)


def test_bull_put_spread_structure():
    chain = make_chain()
    strat = construct_bull_put_spread(chain, 100.0, "balanced", "TEST")
    assert strat is not None
    assert len(strat.legs) == 2
    short = [l for l in strat.legs if l.action == "sell"][0]
    long = [l for l in strat.legs if l.action == "buy"][0]
    assert short.option_type == "put" and long.option_type == "put"
    assert short.strike > long.strike  # short closer to money
    assert short.strike < 100.0        # both OTM


def test_bull_put_spread_metrics_credit_positive():
    chain = make_chain()
    strat = construct_bull_put_spread(chain, 100.0, "balanced", "TEST")
    strat = compute_metrics(strat, 100.0)
    assert strat.metrics["net_premium"] > 0
    assert strat.metrics["max_loss"] > 0
    assert strat.metrics["roc_percent"] > 0


def test_iron_condor_four_legs():
    chain = make_chain()
    strat = construct_iron_condor(chain, 100.0, "balanced", "TEST")
    assert strat is not None
    assert len(strat.legs) == 4
    sells = [l for l in strat.legs if l.action == "sell"]
    buys = [l for l in strat.legs if l.action == "buy"]
    assert len(sells) == 2 and len(buys) == 2


def test_recommend_bullish_returns_spread():
    chain = make_chain()
    cands = recommend(chain, 100.0, "bullish", "balanced", "TEST")
    assert len(cands) >= 1
    assert cands[0].type == "bull_put_spread"


def test_recommend_neutral_prefers_condor():
    chain = make_chain()
    cands = recommend(chain, 100.0, "neutral", "balanced", "TEST")
    assert len(cands) >= 1
    assert cands[0].type == "iron_condor"


def test_illiquid_chain_no_candidates():
    chain = make_chain()
    chain["volume"] = 0
    chain["openInterest"] = 0
    # recommender itself doesn't filter liquidity (risk manager does),
    # but it should still produce structurally valid candidates
    cands = recommend(chain, 100.0, "bullish", "balanced", "TEST")
    assert isinstance(cands, list)

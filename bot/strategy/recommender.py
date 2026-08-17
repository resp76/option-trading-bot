"""Theta-Gang strategy recommender.

Adapted from EconomiaUNMSM/OptionStrat-AI (app/services/strategy_recommender.py).
Builds defined-risk credit structures from a directional bias:
  bullish  -> Bull Put Spread
  bearish  -> Bear Call Spread
  neutral  -> Iron Condor
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from ..models import Leg, Strategy

RISK_PARAMS = {
    "conservative": {"sell_delta": 0.15, "buy_delta": 0.05, "wing_width": 5},
    "balanced":     {"sell_delta": 0.20, "buy_delta": 0.10, "wing_width": 10},
    "aggressive":   {"sell_delta": 0.30, "buy_delta": 0.15, "wing_width": 15},
}


def _find_closest_strike(df: pd.DataFrame, target_delta: float) -> Optional[pd.Series]:
    if df.empty or "delta" not in df.columns:
        return None
    df = df.copy()
    df["diff"] = abs(abs(df["delta"]) - target_delta)
    return df.sort_values("diff").iloc[0]


def _find_strike_at(df: pd.DataFrame, target_strike: float) -> Optional[pd.Series]:
    if df.empty:
        return None
    df = df.copy()
    df["diff"] = abs(df["strike"] - target_strike)
    return df.sort_values("diff").iloc[0]


def _format_leg(row: pd.Series, action: str, ticker: str) -> Leg:
    premium = float(row.get("mid_price", 0.0) or 0.0)
    if premium <= 0:
        premium = float(row.get("lastPrice", 0.0) or 0.0)
    if premium <= 0:
        bid = float(row.get("bid", 0.0) or 0.0)
        ask = float(row.get("ask", 0.0) or 0.0)
        if bid > 0 or ask > 0:
            premium = (bid + ask) / 2.0
    if premium <= 0:
        premium = 0.01

    return Leg(
        ticker=ticker,
        option_type=str(row["optionType"]),
        strike=float(row["strike"]),
        expiration=str(row["expiration"]),
        action=action,
        qty=1,
        premium=premium,
        iv=float(row.get("impliedVolatility") or 0.0) or None,
        delta=float(row.get("delta") or 0.0) or None,
        bid=float(row.get("bid", 0.0) or 0.0),
        ask=float(row.get("ask", 0.0) or 0.0),
        volume=int(row.get("volume", 0)),
        open_interest=int(row.get("openInterest", 0)),
    )


def construct_bull_put_spread(chain_df: pd.DataFrame, spot: float,
                              risk_profile: str, ticker: str) -> Optional[Strategy]:
    risk = RISK_PARAMS.get(risk_profile, RISK_PARAMS["balanced"])
    puts = chain_df[(chain_df["optionType"] == "put") & (chain_df["strike"] < spot)].copy()
    if puts.empty:
        return None
    short_put = _find_closest_strike(puts, risk["sell_delta"])
    if short_put is None:
        return None
    long_puts = puts[puts["strike"] < short_put["strike"]]
    if long_puts.empty:
        return None
    long_put = _find_strike_at(long_puts, short_put["strike"] - risk["wing_width"])
    if long_put is None:
        return None
    return Strategy(
        name="Bull Put Spread", type="bull_put_spread", ticker=ticker, bias="bullish",
        legs=[_format_leg(short_put, "sell", ticker), _format_leg(long_put, "buy", ticker)],
    )


def construct_bear_call_spread(chain_df: pd.DataFrame, spot: float,
                               risk_profile: str, ticker: str,
                               forced_width: Optional[float] = None) -> Optional[Strategy]:
    risk = RISK_PARAMS.get(risk_profile, RISK_PARAMS["balanced"])
    width = forced_width if forced_width else risk["wing_width"]
    calls = chain_df[(chain_df["optionType"] == "call") & (chain_df["strike"] > spot)].copy()
    if calls.empty:
        return None
    short_call = _find_closest_strike(calls, risk["sell_delta"])
    if short_call is None:
        return None
    long_calls = calls[calls["strike"] > short_call["strike"]]
    if long_calls.empty:
        return None
    long_call = _find_strike_at(long_calls, short_call["strike"] + width)
    if long_call is None:
        return None
    return Strategy(
        name="Bear Call Spread", type="bear_call_spread", ticker=ticker, bias="bearish",
        legs=[_format_leg(short_call, "sell", ticker), _format_leg(long_call, "buy", ticker)],
    )


def construct_iron_condor(chain_df: pd.DataFrame, spot: float,
                          risk_profile: str, ticker: str) -> Optional[Strategy]:
    bull = construct_bull_put_spread(chain_df, spot, risk_profile, ticker)
    if not bull:
        return None
    put_width = abs(bull.legs[0].strike - bull.legs[1].strike)
    if put_width <= 0:
        return None
    bear = construct_bear_call_spread(chain_df, spot, risk_profile, ticker, forced_width=put_width)
    if not bear:
        return None
    call_width = abs(bear.legs[1].strike - bear.legs[0].strike)
    if min(put_width, call_width) > 0:
        if max(put_width, call_width) / min(put_width, call_width) > 1.5:
            return None
    return Strategy(
        name="Iron Condor", type="iron_condor", ticker=ticker, bias="neutral",
        legs=bull.legs + bear.legs,
    )


def compute_metrics(strategy: Strategy, spot: float) -> Strategy:
    """Fill strategy.metrics with net_premium, max_loss, margin_req, roc_percent."""
    legs = strategy.legs
    total_credit = strategy.net_premium

    max_loss = 0.0
    buying_power = 0.0
    sell_legs = [l for l in legs if l.action == "sell"]
    buy_legs = [l for l in legs if l.action == "buy"]

    if len(legs) == 4 and len(sell_legs) == 2 and len(buy_legs) == 2:
        put_strikes = [l.strike for l in legs if l.option_type == "put"]
        call_strikes = [l.strike for l in legs if l.option_type == "call"]
        put_width = abs(put_strikes[0] - put_strikes[1]) * 100
        call_width = abs(call_strikes[0] - call_strikes[1]) * 100
        wider = max(put_width, call_width)
        max_loss = wider - total_credit
        buying_power = max_loss
    elif len(legs) == 2 and len(sell_legs) == 1 and len(buy_legs) == 1:
        width = abs(legs[0].strike - legs[1].strike) * 100
        max_loss = width - total_credit
        buying_power = max_loss
    elif len(legs) == 2 and len(sell_legs) == 2:
        max_loss = float("inf")
        buying_power = spot * 0.20 * 100

    roc = (total_credit / buying_power * 100) if buying_power > 0 and max_loss > 0 else 0.0
    strategy.metrics = {
        "net_premium": round(total_credit, 2),
        "max_loss": round(max_loss, 2) if max_loss != float("inf") else "Unlimited",
        "margin_req": round(buying_power, 2),
        "roc_percent": round(roc, 2),
    }
    return strategy


def recommend(chain_df: pd.DataFrame, spot: float, bias: str,
              risk_profile: str, ticker: str) -> list[Strategy]:
    """Entry point: return candidate strategies for a bias, best ROC first.

    Strategies are built per-expiration only — a spread/condor must never mix
    expirations across legs (that would create calendar risk and break the
    max-loss math).
    """
    candidates: list[Strategy] = []

    for exp, exp_chain in chain_df.groupby("expiration"):
        if bias == "bullish":
            s = construct_bull_put_spread(exp_chain, spot, risk_profile, ticker)
            if s:
                candidates.append(compute_metrics(s, spot))
        elif bias == "bearish":
            s = construct_bear_call_spread(exp_chain, spot, risk_profile, ticker)
            if s:
                candidates.append(compute_metrics(s, spot))
        elif bias == "neutral":
            ic = construct_iron_condor(exp_chain, spot, risk_profile, ticker)
            if ic:
                candidates.append(compute_metrics(ic, spot))
            else:
                bull = construct_bull_put_spread(exp_chain, spot, risk_profile, ticker)
                bear = construct_bear_call_spread(exp_chain, spot, risk_profile, ticker)
                if bull:
                    candidates.append(compute_metrics(bull, spot))
                if bear:
                    candidates.append(compute_metrics(bear, spot))

    # only credit structures with positive premium
    candidates = [c for c in candidates if c.metrics["net_premium"] > 0]
    candidates.sort(key=lambda c: c.metrics["roc_percent"], reverse=True)
    return candidates

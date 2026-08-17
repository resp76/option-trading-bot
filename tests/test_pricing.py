"""Unit tests for the pricing engine."""
import math

from bot.pricing.black_scholes import binomial_tree_price, bsm_greeks, bsm_price


def test_bsm_call_price_reasonable():
    # ATM call, 30% vol, 1y, r=0: should be roughly 0.4*S*sigma*sqrt(T) ~ 12
    price = bsm_price(S=100, K=100, T=1.0, r=0.0, sigma=0.30, kind="call")
    assert 10 < price < 15


def test_bsm_put_call_parity():
    S, K, T, r = 100, 100, 0.5, 0.05
    c = bsm_price(S, K, T, r, 0.25, kind="call")
    p = bsm_price(S, K, T, r, 0.25, kind="put")
    lhs = c - p
    rhs = S - K * math.exp(-r * T)
    assert abs(lhs - rhs) < 1e-6


def test_bsm_intrinsic_at_expiry():
    assert bsm_price(110, 100, 0.0, 0.05, 0.3, kind="call") == 10.0
    assert bsm_price(90, 100, 0.0, 0.05, 0.3, kind="put") == 10.0


def test_greeks_call_delta_range():
    g = bsm_greeks(100, 100, 0.5, 0.03, 0.25, kind="call")
    assert 0.4 < g["delta"] < 0.7
    assert g["gamma"] > 0
    assert g["vega"] > 0
    assert g["theta"] < 0  # time decay hurts long calls


def test_greeks_put_delta_negative():
    g = bsm_greeks(100, 100, 0.5, 0.03, 0.25, kind="put")
    assert -0.7 < g["delta"] < -0.3


def test_binomial_converges_to_bsm_european():
    bsm = bsm_price(100, 100, 0.5, 0.03, 0.25, kind="call")
    tree = binomial_tree_price(100, 100, 0.5, 0.03, 0.25, N=300, kind="call", style="european")
    assert abs(bsm - tree) < 0.5


def test_binomial_american_put_premium():
    # American put should be >= European put
    euro = binomial_tree_price(100, 100, 1.0, 0.05, 0.3, N=200, kind="put", style="european")
    amer = binomial_tree_price(100, 100, 1.0, 0.05, 0.3, N=200, kind="put", style="american")
    assert amer >= euro - 1e-9

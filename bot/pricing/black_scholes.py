"""Black-Scholes-Merton pricing engine.

Adapted from EconomiaUNMSM/OptionStrat-AI (app/core/black_scholes.py), MIT-licensed.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import norm


def bsm_price(S: float, K: float, T: float, r: float, sigma: float,
              q: float = 0.0, kind: str = "call") -> float:
    """European option price via Black-Scholes-Merton."""
    if kind == "stock":
        return float(S)
    if T <= 0 or sigma <= 0:
        return max(0.0, (S - K) if kind == "call" else (K - S))

    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)

    if kind == "call":
        return float(S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1))


def bsm_greeks(S: float, K: float, T: float, r: float, sigma: float,
               q: float = 0.0, kind: str = "call") -> dict:
    """Delta, Gamma, Theta (per day), Vega (per 1% vol), Rho via BSM."""
    if kind == "stock":
        return {"delta": 1.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}
    if T <= 0 or sigma <= 0:
        return {"delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0, "rho": 0.0}

    sqrt_T = np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    pdf_d1 = norm.pdf(d1)
    gamma = (np.exp(-q * T) * pdf_d1) / (S * sigma * sqrt_T)
    vega = S * np.exp(-q * T) * pdf_d1 * sqrt_T / 100.0

    if kind == "call":
        delta = np.exp(-q * T) * norm.cdf(d1)
        term1 = -(S * sigma * np.exp(-q * T) * pdf_d1) / (2 * sqrt_T)
        term2 = -r * K * np.exp(-r * T) * norm.cdf(d2)
        term3 = q * S * np.exp(-q * T) * norm.cdf(d1)
        rho = (K * T * np.exp(-r * T) * norm.cdf(d2)) / 100.0
    else:
        delta = -np.exp(-q * T) * norm.cdf(-d1)
        term1 = -(S * sigma * np.exp(-q * T) * pdf_d1) / (2 * sqrt_T)
        term2 = r * K * np.exp(-r * T) * norm.cdf(-d2)
        term3 = -q * S * np.exp(-q * T) * norm.cdf(-d1)
        rho = (-K * T * np.exp(-r * T) * norm.cdf(-d2)) / 100.0

    theta = (term1 + term2 + term3) / 365.0
    return {"delta": float(delta), "gamma": float(gamma), "theta": float(theta),
            "vega": float(vega), "rho": float(rho)}


def binomial_tree_price(S: float, K: float, T: float, r: float, sigma: float,
                        N: int = 100, q: float = 0.0, kind: str = "call",
                        style: str = "american") -> float:
    """Cox-Ross-Rubinstein binomial tree; supports American exercise."""
    if T <= 0:
        return max(0.0, (S - K) if kind == "call" else (K - S))

    dt = T / N
    u = np.exp(sigma * np.sqrt(dt))
    d = 1 / u
    p = (np.exp((r - q) * dt) - d) / (u - d)
    disc = np.exp(-r * dt)

    ST = S * d ** np.arange(N, -1, -1) * u ** np.arange(0, N + 1)
    C = np.maximum(0, ST - K) if kind == "call" else np.maximum(0, K - ST)

    for i in range(N - 1, -1, -1):
        C = disc * (p * C[1:] + (1 - p) * C[:-1])
        if style == "american":
            Si = S * d ** np.arange(i, -1, -1) * u ** np.arange(0, i + 1)
            exercise = np.maximum(0, Si - K) if kind == "call" else np.maximum(0, K - Si)
            C = np.maximum(C, exercise)

    return float(C[0])

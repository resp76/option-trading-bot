from __future__ import annotations

import numpy as np
from numba import njit

@njit
def bsm_price_numba(S, K, T, r, sigma, q=0.0, kind=1):
    # kind: 1=call, 0=put
    if T <= 0 or sigma <= 0:
        if kind == 1:
            return max(0.0, S - K)
        else:
            return max(0.0, K - S)
    sqrtT = np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * sqrtT)
    d2 = d1 - sigma * sqrtT
    # approximate norm.cdf via error function for speed
    cdf_d1 = 0.5 * (1.0 + np.math.erf(d1 / np.sqrt(2.0)))
    cdf_d2 = 0.5 * (1.0 + np.math.erf(d2 / np.sqrt(2.0)))
    if kind == 1:
        return S * np.exp(-q * T) * cdf_d1 - K * np.exp(-r * T) * cdf_d2
    else:
        return K * np.exp(-r * T) * (1 - cdf_d2) - S * np.exp(-q * T) * (1 - cdf_d1)

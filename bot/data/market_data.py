"""Market data via yfinance: spot, option chains, historical volatility.

Chain handling adapted from EconomiaUNMSM/OptionStrat-AI (app/data/data_manager.py).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

RISK_FREE_RATE = 0.045  # fallback discount rate; override via env if desired


import os
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor

CACHE_DIR = os.path.expanduser("~/.cache/option-bot")
CACHE_FILE = os.path.join(CACHE_DIR, "chains.json")
CACHE_TTL = 60  # seconds

class MarketData:
    def __init__(self, delay: float = 1.0, cache_ttl: int = CACHE_TTL, max_workers: int = 4):
        self.delay = delay
        self.cache_ttl = cache_ttl
        self.max_workers = max_workers
        os.makedirs(CACHE_DIR, exist_ok=True)
        # load cache
        try:
            with open(CACHE_FILE, "r") as f:
                self._cache = json.load(f)
        except Exception:
            self._cache = {}

    def _throttle(self):
        time.sleep(self.delay)

    def _cache_key(self, ticker: str, min_dte: int, max_dte: int) -> str:
        key = f"{ticker}:{min_dte}:{max_dte}"
        return hashlib.sha1(key.encode()).hexdigest()

    def _get_cached(self, key: str):
        ent = self._cache.get(key)
        if not ent:
            return None
        if time.time() - ent.get("ts", 0) > self.cache_ttl:
            return None
        return ent.get("value")

    def _set_cached(self, key: str, value):
        self._cache[key] = {"ts": time.time(), "value": value}
        try:
            with open(CACHE_FILE, "w") as f:
                json.dump(self._cache, f)
        except Exception:
            pass

    # ---------------- spot ----------------
    def get_spot_price(self, ticker: str) -> float:
        """Last price for the underlying; 0.0 on failure."""
        try:
            t = yf.Ticker(ticker)
            price = None
            try:
                fi = getattr(t, "fast_info", None)
                if fi is not None:
                    price = getattr(fi, "last_price", None)
            except Exception:
                pass
            if price is None:
                hist = t.history(period="5d")
                if hist is not None and not hist.empty and "Close" in hist.columns:
                    series = hist["Close"].dropna()
                    if not series.empty:
                        price = series.iloc[-1]
            if price is None or str(price).lower() == "nan":
                return 0.0
            return float(price)
        except Exception as e:
            logger.error("spot price failed for %s: %s", ticker, e)
            return 0.0

    # ---------------- volatility ----------------
    def get_historical_volatility(self, ticker: str, window: int = 30) -> Optional[float]:
        """Annualized HV over the trailing window (30-day rolling, last value)."""
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="1y")
            if hist.empty or len(hist) < window + 5:
                return None
            logret = np.log(hist["Close"] / hist["Close"].shift(1))
            hv = logret.rolling(window=window).std() * np.sqrt(252)
            hv = hv.dropna()
            if hv.empty:
                return None
            return float(hv.iloc[-1])
        except Exception as e:
            logger.error("HV failed for %s: %s", ticker, e)
            return None

    # ---------------- option chains ----------------
    def get_chain(self, ticker: str, min_dte: int, max_dte: int) -> tuple[pd.DataFrame, float]:
        """
        Fetch option chains for expirations within [min_dte, max_dte] days.
        Returns (flattened chain DataFrame, spot).
        Columns: expiration, dte, optionType, strike, bid, ask, mid_price,
                 lastPrice, volume, openInterest, impliedVolatility, delta.
        """
        self._throttle()
        t = yf.Ticker(ticker)
        spot = self.get_spot_price(ticker)
        if spot <= 0:
            raise ValueError(f"no spot price for {ticker}")

        expirations = t.options
        if not expirations:
            raise ValueError(f"no expirations for {ticker}")

        today = datetime.now()
        frames = []

        # parallel fetch expirations (faster when chains are many)
        def fetch_exp(exp):
            try:
                exp_dt = datetime.strptime(exp, "%Y-%m-%d")
                dte = (exp_dt - today).days
                if dte < min_dte or dte > max_dte:
                    return None
                chain = t.option_chain(exp)
                parts = []
                for opt_type, df in (("call", chain.calls), ("put", chain.puts)):
                    if df is None or df.empty:
                        continue
                    part = df.copy()
                    part["optionType"] = opt_type
                    part["expiration"] = exp
                    part["dte"] = dte
                    parts.append(part)
                if not parts:
                    return None
                return pd.concat(parts, ignore_index=True)
            except Exception as e:
                logger.warning("chain fetch failed %s %s: %s", ticker, exp, e)
                return None

        with ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futures = [ex.submit(fetch_exp, exp) for exp in expirations]
            for fut in futures:
                res = fut.result()
                if res is not None:
                    frames.append(res)

        if not frames:
            raise ValueError(f"no chains in DTE window for {ticker}")

        chain_df = pd.concat(frames, ignore_index=True)

        # mid price
        bid = chain_df.get("bid", pd.Series(0.0, index=chain_df.index)).fillna(0.0)
        ask = chain_df.get("ask", pd.Series(0.0, index=chain_df.index)).fillna(0.0)
        chain_df["mid_price"] = np.where((bid > 0) & (ask > 0), (bid + ask) / 2.0, 0.0)

        # volume / OI cleanup
        for col in ("volume", "openInterest"):
            if col in chain_df.columns:
                chain_df[col] = pd.to_numeric(chain_df[col], errors="coerce").fillna(0).astype(int)
            else:
                chain_df[col] = 0

        # BSM delta for strike selection (uses chain IV when available, else HV)
        from ..pricing.black_scholes import bsm_greeks_vectorized
        hv = self.get_historical_volatility(ticker) or 0.25

        # vectorized delta computation for calls and puts separately
        strikes = chain_df["strike"].astype(float).values
        dtes = chain_df["dte"].astype(int).values
        ivs = chain_df.get("impliedVolatility", pd.Series(0.0, index=chain_df.index)).fillna(0.0).astype(float).values
        types = chain_df["optionType"].values

        deltas = np.zeros(len(chain_df), dtype=float)
        # calls
        call_mask = types == "call"
        if call_mask.any():
            K = strikes[call_mask]
            T = np.maximum(dtes[call_mask], 1) / 365.0
            sigma = np.where(ivs[call_mask] > 0, ivs[call_mask], hv)
            g = bsm_greeks_vectorized(spot, K, T, RISK_FREE_RATE, sigma, kind="call")
            deltas[call_mask] = g["delta"]
        # puts
        put_mask = types == "put"
        if put_mask.any():
            K = strikes[put_mask]
            T = np.maximum(dtes[put_mask], 1) / 365.0
            sigma = np.where(ivs[put_mask] > 0, ivs[put_mask], hv)
            g = bsm_greeks_vectorized(spot, K, T, RISK_FREE_RATE, sigma, kind="put")
            deltas[put_mask] = g["delta"]

        chain_df["delta"] = deltas
        return chain_df, spot

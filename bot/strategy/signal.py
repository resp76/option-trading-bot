"""Signal generation: blend news sentiment with price momentum into a bias."""
from __future__ import annotations

import logging

import yfinance as yf

from ..sentiment.finviz_sentiment import get_recent_sentiment

logger = logging.getLogger(__name__)

# thresholds
SENTIMENT_BULL = 0.15
SENTIMENT_BEAR = -0.15
MOMENTUM_BULL = 0.01    # +1% over lookback
MOMENTUM_BEAR = -0.01


def get_momentum(ticker: str, lookback_days: int = 10) -> float:
    """Fractional price change over the trailing N trading days (0.0 on failure)."""
    try:
        hist = yf.Ticker(ticker).history(period=f"{lookback_days}d")
        if hist is None or hist.empty or len(hist) < 2:
            return 0.0
        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return 0.0
        return float(closes.iloc[-1] / closes.iloc[0] - 1.0)
    except Exception as e:
        logger.error("momentum failed for %s: %s", ticker, e)
        return 0.0


def compute_bias(ticker: str, sentiment_weight: float = 0.6) -> dict:
    """
    Combine sentiment (Finviz/VADER) and momentum into a composite score in [-1, 1].

    Returns {"bias": bullish|bearish|neutral, "score": float,
             "sentiment": {...}, "momentum": float}
    """
    sentiment = get_recent_sentiment(ticker)
    momentum = get_momentum(ticker)

    s = sentiment.get("score", 0.0)
    # clamp momentum contribution to [-1, 1] (±5% move saturates)
    m = max(-1.0, min(1.0, momentum / 0.05))

    score = sentiment_weight * s + (1.0 - sentiment_weight) * m

    if score >= SENTIMENT_BULL and (s > 0 or m > MOMENTUM_BULL):
        bias = "bullish"
    elif score <= SENTIMENT_BEAR and (s < 0 or m < MOMENTUM_BEAR):
        bias = "bearish"
    else:
        bias = "neutral"

    return {"bias": bias, "score": round(score, 4), "sentiment": sentiment,
            "momentum": round(momentum, 4)}

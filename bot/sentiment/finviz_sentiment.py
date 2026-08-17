"""News sentiment via Finviz + VADER.

Adapted from EconomiaUNMSM/OptionStrat-AI (app/services/sentiment_analyzer.py).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
except ImportError:  # pragma: no cover
    SentimentIntensityAnalyzer = None

logger = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def get_recent_sentiment(ticker: str, days: int = 5, timeout: int = 10) -> dict:
    """
    Scrape Finviz news headlines for a ticker, score with VADER,
    average compound score over the last N days.

    Returns: {"score": float [-1..1], "news_count": int,
              "recent_headlines": [...], "status": str}
    """
    url = "https://finviz.com/quote.ashx?t={}&p=d".format(ticker)
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.content, "html5lib")
        news_table = soup.find(id="news-table")
        if not news_table:
            return {"score": 0.0, "news_count": 0, "status": "no_news"}

        rows = []
        for tr in news_table.find_all("tr"):
            a_tag = tr.find("a", attrs={"class": "tab-link-news"})
            td_tag = tr.find("td")
            if not a_tag or not td_tag:
                continue
            headline = a_tag.text
            parts = td_tag.text.replace("\n", "").strip().split()
            if len(parts) >= 2:
                date_str = parts[0]
                if date_str.lower() == "today":
                    date_str = datetime.now().strftime("%b-%d-%y")
            elif len(parts) == 1:
                date_str = datetime.now().strftime("%b-%d-%y")
            else:
                continue
            rows.append([ticker, date_str, headline])

        if not rows:
            return {"score": 0.0, "news_count": 0, "status": "no_news"}

        df = pd.DataFrame(rows, columns=["Ticker", "Fecha", "Titular"])
        df["Fecha"] = pd.to_datetime(df["Fecha"], format="%b-%d-%y", errors="coerce")
        df = df.dropna(subset=["Fecha"])
        if df.empty or SentimentIntensityAnalyzer is None:
            return {"score": 0.0, "news_count": len(df), "status": "no_analyzer"}

        sia = SentimentIntensityAnalyzer()
        df["Sentimiento"] = df["Titular"].apply(lambda x: sia.polarity_scores(x)["compound"])

        # keep only the last N days
        cutoff = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
        recent = df[df["Fecha"] >= cutoff]
        source = recent if not recent.empty else df
        avg = source["Sentimiento"].mean()
        if pd.isna(avg):
            avg = 0.0

        return {
            "score": float(avg),
            "news_count": len(df),
            "recent_headlines": df["Titular"].head(5).tolist(),
            "status": "success",
        }
    except Exception as e:
        logger.error("sentiment failed for %s: %s", ticker, e)
        return {"score": 0.0, "news_count": 0, "status": "error", "message": str(e)}

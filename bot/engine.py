"""Trading bot engine: wires data -> signal -> strategy -> risk -> broker -> exits."""
from __future__ import annotations

import logging

from .ai.analyst import ai_review
from .broker.paper_broker import PaperBroker
from .data.market_data import MarketData
from .risk.exit_manager import manage_exits
from .risk.risk_manager import RiskManager
from .strategy import recommender
from .strategy.signal import compute_bias

logger = logging.getLogger(__name__)


class TradingBot:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.data = MarketData()
        self.broker = PaperBroker(starting_capital=float(cfg.get("starting_capital", 100_000)))
        self.risk = RiskManager(cfg)

    def scan_ticker(self, ticker: str) -> dict:
        """Run one full cycle for a ticker. Returns a report dict."""
        report = {"ticker": ticker, "actions": [], "skipped": [], "error": None}

        try:
            # 1) Fetch chain + spot
            chain_df, spot = self.data.get_chain(
                ticker,
                min_dte=int(self.cfg.get("min_dte", 20)),
                max_dte=int(self.cfg.get("max_dte", 60)),
            )
            logger.info("%s spot=%.2f chain_rows=%d", ticker, spot, len(chain_df))

            # 2) Manage exits first (uses full chain)
            closed = manage_exits(self.broker, chain_df, self.cfg)
            report["actions"].extend(closed)

            # 3) Signal
            signal = compute_bias(ticker)
            report["signal"] = {
                "bias": signal["bias"], "score": signal["score"],
                "momentum": signal["momentum"],
                "sentiment": signal["sentiment"].get("score"),
                "news_count": signal["sentiment"].get("news_count"),
            }
            logger.info("%s bias=%s score=%.3f momentum=%.3f sentiment=%.3f",
                        ticker, signal["bias"], signal["score"],
                        signal["momentum"], signal["sentiment"].get("score", 0.0))

            # 4) Strategy candidates
            candidates = recommender.recommend(
                chain_df, spot, signal["bias"],
                self.cfg.get("risk_profile", "balanced"), ticker,
            )
            if not candidates:
                report["skipped"].append("no viable strategy for bias")
                return report

            best = candidates[0]
            report["candidate"] = {
                "name": best.name, "type": best.type,
                "net_premium": best.metrics["net_premium"],
                "max_loss": best.metrics["max_loss"],
                "roc_percent": best.metrics["roc_percent"],
                "legs": [
                    {"action": l.action, "type": l.option_type, "strike": l.strike,
                     "exp": l.expiration, "premium": round(l.premium, 2),
                     "vol": l.volume, "oi": l.open_interest}
                    for l in best.legs
                ],
            }

            # 5) Risk gate
            ok, reason = self.risk.check(best, self.broker.account, spot)
            if not ok:
                report["skipped"].append(f"risk: {reason}")
                return report

            # 6) Optional AI veto
            approved, ai_reason = ai_review(best, signal, self.cfg)
            report["ai_review"] = {"approved": approved, "reasoning": ai_reason}
            if not approved:
                report["skipped"].append(f"ai_veto: {ai_reason}")
                return report

            # 7) Execute on paper
            pos = self.broker.open_position(best)
            report["actions"].append(
                f"OPENED {best.name} id={pos.id} credit=${pos.entry_credit:.2f}"
            )
            return report

        except Exception as e:
            logger.exception("scan failed for %s", ticker)
            report["error"] = str(e)
            return report

    def run_cycle(self) -> list[dict]:
        reports = []
        for ticker in self.cfg.get("tickers", []):
            logger.info("=== scanning %s ===", ticker)
            reports.append(self.scan_ticker(ticker))
        return reports

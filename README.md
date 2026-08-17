# Option Trading Bot

An autonomous **paper-trading** options bot built on top of the quant stack from
[EconomiaUNMSM/OptionStrat-AI](https://github.com/EconomiaUNMSM/OptionStrat-AI) —
Black-Scholes pricing, Finviz/VADER news sentiment, and the "Theta Gang" strategy
recommender — wired into a trading loop with risk management and a paper broker.

> ⚠️ **This bot trades with PAPER MONEY ONLY by default.** Live broker execution is
> intentionally NOT wired up. Options are leveraged instruments; do not connect real
> money without extensive testing and your own risk review.

## How it works

```
┌────────────┐   ┌──────────────┐   ┌───────────────┐   ┌────────────┐   ┌──────────────┐
│ Market Data │──▶│   Signal      │──▶│  Strategy      │──▶│ Risk Gate   │──▶│ Paper Broker  │
│ (yfinance)  │   │ (sentiment +  │   │ Recommender    │   │ (sizing,    │   │ (simulated    │
│ spot, chain │   │  momentum)    │   │ (spreads,      │   │  caps, POP) │   │  fills, P&L)  │
└────────────┘   └──────────────┘   │  condors)      │   └────────────┘   └──────────────┘
                                     └───────────────┘          │                  │
                                                                ▼                  ▼
                                                          ┌────────────┐   ┌──────────────┐
                                                          │ AI Analyst  │   │ Exit Manager  │
                                                          │ (optional   │   │ (TP / SL /    │
                                                          │  LLM veto)  │   │  expiry)      │
                                                          └────────────┘   └──────────────┘
```

Each cycle, per configured ticker:

1. **Data** — spot price, option chain (bid/ask/IV/volume/OI), historical volatility.
2. **Signal** — combines news sentiment (Finviz + VADER, from OptionStrat-AI) with
   short-term price momentum into a directional bias: `bullish` / `bearish` / `neutral`.
3. **Strategy** — the Theta-Gang recommender picks a defined-risk structure for the bias:
   - Bullish → **Bull Put Spread** (credit)
   - Bearish → **Bear Call Spread** (credit)
   - Neutral → **Iron Condor**
   Liquidity filters (volume > 10, OI > 50) and delta targets follow the upstream logic.
4. **Risk gate** — max open positions, max capital at risk, min credit, liquidity checks,
   no undefined-risk structures by default.
5. **Optional AI analyst** — an LLM can review the proposed trade and veto it
   (works with any OpenAI-compatible endpoint, e.g. OpenCode Go).
6. **Execution** — paper fills at the mid price; state persisted to `state/paper_portfolio.json`.
7. **Exit management** — open positions are re-priced every cycle and closed on:
   profit target (default 50% of credit), stop loss (default 200% of credit), or
   approaching expiration (default ≤ 2 days to expiry).

## Quick start

```bash
cd option-trading-bot
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp config.example.yaml config.yaml
cp .env.example .env        # optional: add OPENAI_API_KEY / LLM base URL for AI veto

# Single scan + trade cycle (safe to run any time)
python run.py --once

# Continuous loop (scans every N minutes, see config)
python run.py --loop

# Portfolio status & P&L
python run.py --status

# Reset the paper account
python run.py --reset
```

## Configuration (`config.yaml`)

| Key | Default | Meaning |
|---|---|---|
| `tickers` | `[SPY, QQQ]` | Underlyings to scan |
| `starting_capital` | `100000` | Paper account balance |
| `risk_profile` | `balanced` | `conservative` / `balanced` / `aggressive` (delta targets) |
| `max_open_positions` | `4` | Position cap |
| `max_positions_per_ticker` | `1` | Per-underlying cap |
| `max_capital_per_trade` | `5000` | Max buying power per spread |
| `min_credit` | `0.50` | Minimum credit per contract ($) |
| `min_volume` / `min_open_interest` | `10` / `50` | Liquidity filters |
| `min_dte` / `max_dte` | `20` / `60` | Expiration window for new trades |
| `profit_target_pct` | `0.50` | Close at 50% of max credit captured |
| `stop_loss_pct` | `2.00` | Close if loss reaches 2x credit |
| `exit_days_before_expiry` | `2` | Close before expiration |
| `scan_interval_minutes` | `30` | Loop frequency |
| `ai_review.enabled` | `false` | LLM veto of proposed trades |

## Tests

```bash
python -m pytest tests/ -v
```

## Credits

- Quant core adapted from [EconomiaUNMSM/OptionStrat-AI](https://github.com/EconomiaUNMSM/OptionStrat-AI)
  (BSM engine, Finviz sentiment, Theta-Gang recommender).
- Data: [yfinance](https://github.com/ranaroussi/yfinance) (delayed quotes — not for live execution).

## Disclaimer

Educational software. No warranty. Not financial advice. Paper broker only; any live
trading integration is left as an exercise and is your sole responsibility.

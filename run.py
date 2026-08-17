#!/usr/bin/env python3
"""Option Trading Bot — CLI entry point.

Usage:
  python run.py --once      Run a single scan/trade cycle
  python run.py --loop      Run continuously (scan_interval_minutes)
  python run.py --status    Show paper portfolio & P&L
  python run.py --reset     Reset the paper account
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

import yaml

from bot.broker.paper_broker import PaperBroker
from bot.engine import TradingBot

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
EXAMPLE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.example.yaml")


def load_config() -> dict:
    path = CONFIG_PATH if os.path.exists(CONFIG_PATH) else EXAMPLE_PATH
    with open(path) as f:
        return yaml.safe_load(f) or {}


def setup_logging(cfg: dict):
    logging.basicConfig(
        level=getattr(logging, str(cfg.get("log_level", "INFO")).upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_once(cfg: dict):
    bot = TradingBot(cfg)
    reports = bot.run_cycle()
    print("\n" + "=" * 60)
    print("CYCLE REPORT")
    print("=" * 60)
    for r in reports:
        print(f"\n[{r['ticker']}]")
        if r.get("error"):
            print(f"  ERROR: {r['error']}")
            continue
        sig = r.get("signal", {})
        print(f"  signal: bias={sig.get('bias')} score={sig.get('score')} "
              f"momentum={sig.get('momentum')} sentiment={sig.get('sentiment')}")
        cand = r.get("candidate")
        if cand:
            print(f"  candidate: {cand['name']} credit=${cand['net_premium']} "
                  f"max_loss={cand['max_loss']} roc={cand['roc_percent']}%")
            for leg in cand["legs"]:
                print(f"    {leg['action'].upper():4} {leg['type']:4} K={leg['strike']} "
                      f"exp={leg['exp']} px={leg['premium']} vol={leg['vol']} oi={leg['oi']}")
        for s in r.get("skipped", []):
            print(f"  skipped: {s}")
        for a in r.get("actions", []):
            print(f"  action: {a}")
        ai = r.get("ai_review")
        if ai:
            print(f"  ai_review: approved={ai['approved']} — {ai['reasoning'][:200]}")
    print("\n" + json.dumps(bot.broker.summary(), indent=2))


def cmd_loop(cfg: dict):
    interval = int(cfg.get("scan_interval_minutes", 30)) * 60
    logging.info("loop mode: scanning every %d minutes. Ctrl+C to stop.", interval // 60)
    while True:
        try:
            bot = TradingBot(cfg)
            bot.run_cycle()
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logging.exception("cycle failed: %s", e)
        logging.info("sleeping %d minutes...", interval // 60)
        time.sleep(interval)


def cmd_status(cfg: dict):
    broker = PaperBroker(starting_capital=float(cfg.get("starting_capital", 100_000)))
    print(json.dumps(broker.summary(), indent=2))


def cmd_reset(cfg: dict):
    broker = PaperBroker(starting_capital=float(cfg.get("starting_capital", 100_000)))
    broker.reset()
    print("Paper account reset.")


def main():
    parser = argparse.ArgumentParser(description="Option Trading Bot (paper)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--once", action="store_true", help="run one cycle")
    group.add_argument("--loop", action="store_true", help="run continuously")
    group.add_argument("--status", action="store_true", help="show portfolio")
    group.add_argument("--reset", action="store_true", help="reset paper account")
    args = parser.parse_args()

    cfg = load_config()
    setup_logging(cfg)

    if args.once:
        cmd_once(cfg)
    elif args.loop:
        cmd_loop(cfg)
    elif args.status:
        cmd_status(cfg)
    elif args.reset:
        cmd_reset(cfg)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nstopped.")
        sys.exit(0)

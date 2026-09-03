#!/usr/bin/env python3
import json, sys
from pathlib import Path
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None
import datetime

# get now in America/New_York
try:
    if ZoneInfo is None:
        raise RuntimeError('zoneinfo unavailable')
    now = datetime.datetime.now(ZoneInfo('America/New_York'))
except Exception as e:
    print(f"ERROR: timezone failure: {e}")
    sys.exit(0)

# market open check: weekday Mon-Fri and between 09:30 and 16:05 inclusive
if now.weekday() >= 5:
    print('SILENT')
    sys.exit(0)

t = now.time()
open_start = datetime.time(9,30)
open_end = datetime.time(16,5)
if not (open_start <= t <= open_end):
    print('SILENT')
    sys.exit(0)

# markets open: read state file
p = Path('state/paper_portfolio.json')
if not p.exists():
    print('ERROR: state/paper_portfolio.json not found')
    sys.exit(0)

try:
    data = json.loads(p.read_text())
except Exception as e:
    print(f'ERROR: could not parse JSON: {e}')
    sys.exit(0)

# helpers
def find_key(d, candidates):
    for k in candidates:
        if k in d:
            return d[k]
    return None

# cash
cash = find_key(data, ['cash','account_cash','cash_balance','balance','starting_cash','starting_capital'])
cash_val = None
if isinstance(cash, (int,float)):
    cash_val = float(cash)
elif isinstance(cash, str):
    try:
        cash_val = float(cash)
    except:
        cash_val = None

if cash_val is None:
    # try nested
    def search_for_number(obj):
        if isinstance(obj,(int,float)):
            return float(obj)
        if isinstance(obj,dict):
            for v in obj.values():
                r = search_for_number(v)
                if r is not None:
                    return r
        return None
    cash_val = search_for_number(data) or 0.0

# realized pnl
realized = find_key(data, ['realized_pnl','realizedPnl','realized','realized_pl','realized_pl_total'])
realized_val = 0.0
if isinstance(realized,(int,float)):
    realized_val = float(realized)
elif isinstance(realized,str):
    try: realized_val = float(realized)
    except: realized_val = 0.0

# positions list
positions = find_key(data, ['positions','open_positions','openPositions','positions_open','portfolio'])
if positions is None:
    # try to find any list of dicts with symbol/ticker
    for v in data.values():
        if isinstance(v, list) and v:
            if isinstance(v[0], dict):
                keys = set(v[0].keys())
                if keys & {'ticker','symbol','id','entry_credit','entryCredit','premium_received'}:
                    positions = v
                    break

if positions is None:
    positions = []

# normalize positions
norm = []
for pos in positions:
    try:
        if not isinstance(pos, dict):
            continue
        pid = pos.get('id') or pos.get('position_id') or pos.get('uid') or pos.get('trade_id') or ''
        ticker = pos.get('ticker') or pos.get('symbol') or pos.get('underlying') or ''
        opened = pos.get('opened_at') or pos.get('openedAt') or pos.get('opened') or pos.get('created_at') or pos.get('createdAt') or ''
        entry_credit = None
        for k in ['entry_credit','entryCredit','premium_received','credit','entry','cost','entry_cost']:
            if k in pos and isinstance(pos[k],(int,float)):
                entry_credit = float(pos[k]); break
            if k in pos and isinstance(pos[k],str):
                try: entry_credit = float(pos[k]); break
                except: pass
        if entry_credit is None:
            entry_credit = 0.0
        unreal = None
        for k in ['unrealized_if_closed','unrealized','unrealized_pnl','unrealizedPnl','mark_to_market','mtm','unrealized_pl','current_pl']:
            if k in pos and isinstance(pos[k],(int,float)):
                unreal = float(pos[k]); break
            if k in pos and isinstance(pos[k],str):
                try: unreal = float(pos[k]); break
                except: pass
        if unreal is None:
            unreal = 0.0
        norm.append({'id':str(pid),'ticker':str(ticker),'opened_at':str(opened),'entry_credit':entry_credit,'unrealized_if_closed':unreal})
    except Exception:
        continue

open_count = len(norm)
entry_credit_total = sum(p['entry_credit'] for p in norm)
unreal_total = sum(p['unrealized_if_closed'] for p in norm)

# prepare message
iso_dt = now.isoformat()
lines = []
lines.append(f"Options bot balance — {iso_dt}")
lines.append(f"- Cash: ${cash_val:,.2f} | Realized P&L: ${realized_val:,.2f}")
lines.append(f"- Open positions: {open_count} | Entry credit: ${entry_credit_total:,.2f} | Unrealized if closed: ${unreal_total:,.2f}")
# up to 3 positions
for p in norm[:3]:
    lines.append(f"- {p['id'] or 'id'} {p['ticker'] or ''} opened {p['opened_at'] or 'N/A'} entry ${p['entry_credit']:.2f} unreal ${p['unrealized_if_closed']:.2f}")

print('\n'.join(lines))

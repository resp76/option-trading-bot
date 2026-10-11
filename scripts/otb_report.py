#!/usr/bin/env python3
import sys, json
from datetime import datetime, time
try:
    from zoneinfo import ZoneInfo
except Exception as e:
    print('ERROR: zoneinfo unavailable')
    sys.exit(2)

tz = ZoneInfo('America/New_York')
now = datetime.now(tz)
iso = now.isoformat()
# Market open window 09:30 to 16:05 inclusive, weekdays
if now.weekday() >= 5:
    print('MARKETS_CLOSED')
    sys.exit(0)
if now.time() < time(9,30) or now.time() > time(16,5):
    print('MARKETS_CLOSED')
    sys.exit(0)

path = 'state/paper_portfolio.json'
try:
    with open(path, 'r') as f:
        data = json.load(f)
except FileNotFoundError:
    print('ERROR: state/paper_portfolio.json not found')
    sys.exit(2)
except json.JSONDecodeError as e:
    msg = str(e).splitlines()[0]
    print(f'ERROR: JSON parse error: {msg}')
    sys.exit(2)

from collections.abc import Mapping, Sequence

def recurse_find_number(obj, keys_lower):
    if isinstance(obj, Mapping):
        for k,v in obj.items():
            if isinstance(k,str) and k.lower() in keys_lower and isinstance(v,(int,float)):
                return float(v)
        for v in obj.values():
            r = recurse_find_number(v, keys_lower)
            if r is not None:
                return r
    elif isinstance(obj, Sequence) and not isinstance(obj,(str,bytes,bytearray)):
        for item in obj:
            r = recurse_find_number(item, keys_lower)
            if r is not None:
                return r
    return None


def find_positions_list(obj):
    # return first plausible positions list
    if isinstance(obj, Mapping):
        for k,v in obj.items():
            if isinstance(v, list) and v:
                # check elements
                if all(isinstance(x, Mapping) for x in v):
                    # heuristic: element has ticker/symbol/underlying or entry_credit
                    first = v[0]
                    keys = set(k.lower() for k in first.keys() if isinstance(k,str))
                    if keys & set(['ticker','symbol','underlying']) or keys & set(['entry_credit','entry','credit']):
                        return v
            # recurse
            r = find_positions_list(v)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for item in obj:
            r = find_positions_list(item)
            if r is not None:
                return r
    return None

cash_keys = set(['cash','account_cash','cash_balance','balance','cashavailable','available_cash'])
realized_keys = set(['realized_pnl','realized_pl','realized','realized_profit','realized_p&l'])
entry_keys = set(['entry_credit','entry','credit','entry_amount','entry_price','initial_credit'])
unrealized_keys = set(['unrealized_pnl','unrealized_pl','unrealized','mark_to_market','mtm','unrealized_if_closed','unrealized_profit','unrealized'])

cash = recurse_find_number(data, cash_keys)
realized = recurse_find_number(data, realized_keys)
positions = find_positions_list(data) or []

# compute per-position
entry_total = 0.0
unreal_total = 0.0
pos_summaries = []
for idx,p in enumerate(positions):
    if not isinstance(p, Mapping):
        continue
    pid = p.get('id') or p.get('position_id') or p.get('uid') or p.get('key') or str(idx)
    ticker = p.get('ticker') or p.get('symbol') or p.get('underlying') or p.get('root') or 'N/A'
    opened = p.get('opened_at') or p.get('opened') or p.get('created_at') or p.get('created') or p.get('openedOn') or 'N/A'
    # entry
    entry = None
    for k in entry_keys:
        if k in p:
            try:
                entry = float(p[k])
            except Exception:
                entry = None
            break
    if entry is None:
        e = recurse_find_number(p, entry_keys)
        if e is not None:
            entry = e
    if entry is None:
        entry = 0.0
    # unreal
    unreal = None
    for k in unrealized_keys:
        if k in p:
            try:
                unreal = float(p[k])
            except Exception:
                unreal = None
            break
    if unreal is None:
        u = recurse_find_number(p, unrealized_keys)
        if u is not None:
            unreal = u
    if unreal is None:
        unreal = 0.0
    entry_total += entry
    unreal_total += unreal
    pos_summaries.append({'id':str(pid),'ticker':str(ticker),'opened_at':str(opened),'entry_credit':entry,'unrealized_if_closed':unreal})


def fmt(x):
    try:
        return f"${x:,.2f}"
    except Exception:
        return 'N/A'

cash_str = fmt(cash) if cash is not None else 'N/A'
realized_str = fmt(realized) if realized is not None else 'N/A'
entry_total_str = fmt(entry_total)
unreal_total_str = fmt(unreal_total)

# build message
lines = []
lines.append(f"Options bot balance — {iso}")
lines.append(f"- Cash: {cash_str}  ·  Realized P&L: {realized_str}")
lines.append(f"- Open positions: {len(pos_summaries)}  ·  Entry credit: {entry_total_str}  ·  Est. unrealized: {unreal_total_str}")
for p in pos_summaries[:3]:
    lines.append(f"- {p['id']} | {p['ticker']} | opened: {p['opened_at']} | entry: {fmt(p['entry_credit'])} | unrealized: {fmt(p['unrealized_if_closed'])}")

print('\n'.join(lines))

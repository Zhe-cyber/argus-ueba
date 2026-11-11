"""Baseline risk score v1: per (account, MYT day), compared with the account's own last 28 days.

Heuristic and fixed-weight. Not trained, not validated, independent of the AE and of
rarity_scorer's off-hours windows. Read-only: opens the SQLite copy with mode=ro.
Method note: docs/LIVE_BASELINE_SCORE_V1.md.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import re
import sqlite3
import statistics

from workspace_next import system_accounts

from backend.rarity_scorer import SENSITIVE_PATTERNS

MYT = timezone(timedelta(hours=8))
WINDOW_DAYS, MIN_HISTORY = 28, 5
WEIGHTS = {'new_action': 0.25, 'new_resource': 0.25, 'unusual_hours': 0.20, 'volume': 0.15, 'sensitive_new': 0.15}
_SENSITIVE = [re.compile(p, re.IGNORECASE) for p in SENSITIVE_PATTERNS]
_CACHE = {}


def tier(score):
    return 'High' if score >= 60 else 'Medium' if score >= 30 else 'Low'


def _stamp(value):
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp without timezone')
    return parsed.astimezone(MYT)


def load(db):
    """{account_key: {'label','kind','source','days': {date: [(hour, source, action, resource)]}}}, cached per file version."""
    path = Path(db).resolve()
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key in _CACHE:
        return _CACHE[key]
    accounts = {}
    with sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True) as con:
        for ak, label, kind, ts, source, action, resource in con.execute(
                'SELECT account_key,account_label,account_kind,timestamp,source,action,resource FROM events '
                'WHERE account_key IS NOT NULL ORDER BY id'):
            try:
                when = _stamp(ts)
            except (ValueError, TypeError):
                continue  # unparseable timestamps are skipped, never guessed
            acct = accounts.setdefault(ak, {'label': label, 'kind': kind, 'source': source, 'days': defaultdict(list)})
            acct['days'][when.date()].append((when.hour, source, action, resource or ''))
    _CACHE.clear()  # one live version at a time
    _CACHE[key] = accounts
    return accounts


def _count_signal(k):
    return 0.0 if k == 0 else 0.6 if k == 1 else 1.0


def _name(value):
    """Display-safe name: request-parameter blobs show their first key only; 12-digit runs masked; max 60 chars."""
    value = str(value)
    if value.startswith('{'):
        m = re.match(r'''\{\s*['"]?([^'":,\s}]+)''', value)
        value = m.group(1) if m else '{...}'
    return re.sub(r'\d{12}', '<account>', value)[:60]


def _short(items, n=3):
    names = sorted({_name(x) for x in items})
    return ', '.join(names[:n]) + (f', +{len(names) - n} more' if len(names) > n else '')


def _rho(sets):
    """Share of evaluable days (4th onward) that introduced >=1 item absent from all earlier days; 0 if < 2 evaluable."""
    seen, hits, n = set(), 0, 0
    for i, s in enumerate(sets):
        if i >= 3:
            n += 1
            hits += bool(s - seen)
        seen |= s
    return (hits / n if n >= 2 else 0.0), hits, n


def score_day(days, day):
    """days: {date: events}. Returns the result dict for `day` (a date with events)."""
    today = days[day]
    prior = sorted(d for d in days if day - timedelta(days=WINDOW_DAYS) <= d < day)
    out = {'day': day.isoformat(), 'history_days': len(prior), 'events_today': len(today),
           'partial': day == datetime.now(MYT).date()}
    if len(prior) < MIN_HISTORY:
        return {**out, 'score': None, 'tier': 'Learning', 'signals': {},
                'facts': [f'{len(prior)} of {MIN_HISTORY} days of history']}
    hist = [e for d in prior for e in days[d]]
    facts, sig = [], {}
    hist_actions = {(e[1], e[2]) for e in hist}
    new_actions = {(e[1], e[2]) for e in today} - hist_actions
    # v1.1 novelty discount: an account that routinely shows new things earns less from newness.
    rho_a, hits_a, n_a = _rho([{(e[1], e[2]) for e in days[d]} for d in prior])
    rho_r, hits_r, n_r = _rho([{e[3] for e in days[d] if e[3]} for d in prior])

    def discount(label, rho, hits, n):
        facts.append(f'This account showed new {label} on {hits} of {n} recent active days, so novelty is discounted.')
    sig['new_action'] = _count_signal(len(new_actions)) * (1 - rho_a)
    if new_actions:
        facts.append(f'{len(new_actions)} action kind(s) never seen in the last {WINDOW_DAYS} days: '
                     + _short([a for _, a in new_actions]))
        if rho_a >= 0.25: discount('actions', rho_a, hits_a, n_a)
    t_res = {e[3] for e in today if e[3]}
    new_res = set()
    if t_res:
        new_res = t_res - {e[3] for e in hist if e[3]}
        sig['new_resource'] = _count_signal(len(new_res)) * (1 - rho_r)
        if new_res:
            facts.append(f'{len(new_res)} resource(s) never seen in the last {WINDOW_DAYS} days: ' + _short(new_res))
            if rho_r >= 0.25: discount('resources', rho_r, hits_r, n_r)
    else:
        sig['new_resource'] = None  # unavailable: weights renormalise
    hours = Counter(e[0] for e in hist)
    core = {h for h, c in hours.items() if c >= 0.05 * len(hist)}
    usual = {(h + k) % 24 for h in core for k in (-1, 0, 1)}  # v1.1: +-1 h, circular
    share = sum(e[0] not in usual for e in today) / len(today)
    sig['unusual_hours'] = min(1.0, share / 0.5)
    if share:
        facts.append(f'{round(share * 100)}% of today\'s events fall outside this account\'s usual hours (MYT)')
    median = statistics.median(len(days[d]) for d in prior)
    ratio = len(today) / median
    sig['volume'] = min(1.0, max(0.0, math.log2(ratio) / 3))
    if sig['volume']:
        facts.append(f'{len(today)} events today; median active day is {median:g} ({ratio:.1f}x)')
    seen = {e[3] for e in hist}
    sens = {r for r in t_res if r not in seen and any(p.search(r) for p in _SENSITIVE)}
    sig['sensitive_new'] = (1.0 if sens else 0.0) * (1 - rho_r)
    if sens:
        facts.append(f'{len(sens)} sensitive resource(s) not seen before: ' + _short(sens))
    avail = {k: v for k, v in sig.items() if v is not None}
    score = round(100 * sum(WEIGHTS[k] * v for k, v in avail.items()) / sum(WEIGHTS[k] for k in avail))
    return {**out, 'score': score, 'tier': tier(score), 'signals': {k: (None if v is None else round(v, 3)) for k, v in sig.items()},
            'rho_action': round(rho_a, 3), 'rho_resource': round(rho_r, 3), 'facts': facts}


def account_days(db, account, days=14):
    """Newest-first scored days for one account, within `days` calendar days of the latest day with events."""
    acct = load(db).get(account)
    latest = latest_day(db)
    if not acct or not latest:
        return []
    floor = latest - timedelta(days=days - 1)
    return [score_day(acct['days'], d) for d in sorted(acct['days'], reverse=True) if d >= floor]


def latest_day(db):
    return max((d for a in load(db).values() for d in a['days']), default=None)


def lookup(db, account, day):
    """{'score','tier'} for one account-day (finding context); Learning when absent."""
    acct = load(db).get(account)
    if not acct or day not in acct['days']:
        return {'tier': 'Learning'}
    r = score_day(acct['days'], day)
    return {'score': r['score'], 'tier': r['tier']}


def summary(db, day=None):
    accounts = load(db)
    day = datetime.strptime(day, '%Y-%m-%d').date() if day else latest_day(db)
    rows, declared = [], system_accounts.declared(db)
    for key, a in accounts.items():
        if day in a['days']:
            r = score_day(a['days'], day)
            rows.append({'account_key': key, 'account_label': a['label'], 'account_kind': a['kind'],
                         'source': a['source'], **r,
                         'infrastructure': system_accounts.is_infrastructure(a['label'], a['kind'], a['source'], declared)})
    rows.sort(key=lambda r: (r['score'] is None, -(r['score'] or 0)))
    return {'day': day.isoformat() if day else None, 'accounts': rows}


def report(db):
    """Counts only: tier per (MYT day, source). No labels, keys or resources."""
    counts = defaultdict(Counter)
    for a in load(db).values():
        for d in a['days']:
            counts[(d.isoformat(), a['source'])][score_day(a['days'], d)['tier']] += 1
    return counts


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--db', required=True)
    ap.add_argument('--report', action='store_true', required=True)
    args = ap.parse_args()
    tiers = ('High', 'Medium', 'Low', 'Learning')
    print('day,source,' + ','.join(tiers))
    for (d, s), c in sorted(report(args.db).items()):
        print(f'{d},{s},' + ','.join(str(c[t]) for t in tiers))

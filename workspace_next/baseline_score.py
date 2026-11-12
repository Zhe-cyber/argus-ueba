"""Workspace view of baseline risk score v1.1. The scorer lives in backend/baseline_scorer.py (one scoring path);
this module re-exports it and READS the stored `baseline_scores` rows of the SQLite copy it is given (mode=ro).

    python -m workspace_next.baseline_score --db <copy> --report    # counts only
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3

from backend.baseline_scorer import (  # noqa: F401  re-exported for workspace code and tests
    ALERT_TYPE, MIN_HISTORY, MYT, WEIGHTS, WINDOW_DAYS, _name, _rho, _short, _stamp, group_days, score_day, tier)
from workspace_next import system_accounts

_CACHE = {}


def _ro(db):
    return sqlite3.connect(f'file:{Path(db).resolve().as_posix()}?mode=ro', uri=True)


def load(db):
    """{account_key: {'label','kind','source','days': {date: [(hour, source, action, resource)]}}} from the events
    table, cached per file version. For timelines, group mapping and rehearsal reports; scores come from the table."""
    path = Path(db).resolve()
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key in _CACHE:
        return _CACHE[key]
    meta, rows = {}, defaultdict(list)
    con = _ro(path)
    try:
        for ak, label, kind, ts, source, action, resource in con.execute(
                'SELECT account_key,account_label,account_kind,timestamp,source,action,resource FROM events '
                'WHERE account_key IS NOT NULL ORDER BY id'):
            meta.setdefault(ak, {'label': label, 'kind': kind, 'source': source})
            rows[ak].append((ts, source, action, resource))
    finally:
        con.close()
    accounts = {}
    for k, m in meta.items():
        days = group_days(rows[k])
        if days:  # an account with no parseable timestamp is not an account-day holder
            accounts[k] = {**m, 'days': days}
    _CACHE.clear()  # one live version at a time
    _CACHE[key] = accounts
    return accounts


def _result(row, today):
    out = {'day': row['day'], 'score': row['score'], 'tier': row['tier'], 'signals': json.loads(row['signals_json']),
           'facts': json.loads(row['facts_json']), 'history_days': row['history_days'],
           'events_today': row['events_today'], 'partial': row['day'] == today}  # partial is "now", not stored time
    if row['tier'] != 'Learning':
        out.update(rho_action=row['rho_action'], rho_resource=row['rho_resource'])
    return out


def _scores(db, where='', args=()):
    today = datetime.now(MYT).date().isoformat()
    con = _ro(db)
    try:
        con.row_factory = sqlite3.Row
        rows = con.execute(f'SELECT * FROM baseline_scores {where}', args).fetchall()
    finally:
        con.close()
    return [(r['account_key'], _result(r, today)) for r in rows]


def _identities(db):
    """{account_key: (label, kind, source)} from each account's first event, as the scorer labels findings."""
    con = _ro(db)
    try:
        return {k: (l, kd, s) for k, l, kd, s in con.execute(
            'SELECT account_key,account_label,account_kind,source FROM events WHERE id IN '
            '(SELECT MIN(id) FROM events WHERE account_key IS NOT NULL GROUP BY account_key)')}
    finally:
        con.close()


def latest_day(db):
    con = _ro(db)
    try:
        value = con.execute('SELECT MAX(day) FROM baseline_scores').fetchone()[0]
    finally:
        con.close()
    return datetime.strptime(value, '%Y-%m-%d').date() if value else None


def account_days(db, account, days=14):
    """Newest-first scored days for one account, within `days` calendar days of the latest scored day."""
    latest = latest_day(db)
    if not latest:
        return []
    floor = (latest - timedelta(days=days - 1)).isoformat()
    return [r for _, r in _scores(db, 'WHERE account_key=? AND day>=? ORDER BY day DESC', (account, floor))]


def lookup(db, account, day):
    """{'score','tier'} for one account-day (finding context); Learning when absent."""
    rows = _scores(db, 'WHERE account_key=? AND day=?', (account, day.isoformat()))
    return {'score': rows[0][1]['score'], 'tier': rows[0][1]['tier']} if rows else {'tier': 'Learning'}


def ml_view(db, account, day):
    """ML anomaly score v2 (backend.live_ae, comparator, never alerts) for one account-day of the copy. Rows written
    by the historical v1 model are not shown."""
    from backend import live_ae
    con = _ro(db)
    try:
        con.row_factory = sqlite3.Row
        row = None
        if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='ml_scores'").fetchone():
            row = con.execute('SELECT * FROM ml_scores WHERE account_key=? AND day=?', (account, day)).fetchone()
            if row is not None and ('model_version' not in row.keys() or row['model_version'] != live_ae.MODEL_VERSION):
                row = None
        events = [] if row else [dict(r) for r in con.execute(
            'SELECT source,metadata,source_account_id,account_kind,resource FROM events WHERE account_key=? ORDER BY id LIMIT 20',
            (account,))]
    finally:
        con.close()
    if row:
        return live_ae.describe(row)
    if live_ae.scope(events) is None:
        return {'status': 'not_applicable', 'reason': live_ae.NOT_APPLICABLE, 'alerting': False}
    return {'status': 'not_scored', 'reason': 'No model score stored for this account-day.', 'alerting': False}


def summary(db, day=None):
    day = datetime.strptime(day, '%Y-%m-%d').date() if day else latest_day(db)
    rows, declared, ident = [], system_accounts.declared(db), _identities(db)
    for key, r in _scores(db, 'WHERE day=?', (day.isoformat() if day else '',)):
        label, kind, source = ident.get(key, (None, None, None))
        rows.append({'account_key': key, 'account_label': label, 'account_kind': kind, 'source': source, **r,
                     'infrastructure': system_accounts.is_infrastructure(label, kind, source, declared)})
    rows.sort(key=lambda r: (r['score'] is None, -(r['score'] or 0)))
    return {'day': day.isoformat() if day else None, 'accounts': rows}


def report(db):
    """Counts only: tier per (MYT day, source). No labels, keys or resources."""
    ident, counts = _identities(db), defaultdict(Counter)
    for key, r in _scores(db):
        counts[(r['day'], ident.get(key, (None, None, None))[2])][r['tier']] += 1
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

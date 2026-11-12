"""Readiness before a live-evaluation check (L7 / L7a): one command, exit code 0 only when everything is ready.

    python -m backend.readiness --db <events.db or workspace copy>

Checks: (1) the baseline method binding file equals the running scorer (baseline_scorer.STATUS); (2) the comparator
loaded by the running deployment (live-ae-loaded.json next to the database, written by backend.live_ae) is the pinned
manifest; (3) no account-day with events lacks its baseline score (and, for lab persona accounts, its v2 ML score);
(4) the score tables have their columns; (5) events dated 13 Nov 2026 MYT or later exist (collection is live);
(6) the declared secondary threshold is in config/live_ae_v2.json and every stored v2 score has its flagged_secondary.
Read-only: it never migrates or scores. Repair: `python -m backend.baseline_scorer --repair-missing --db <db>` and
`python -m backend.live_ae repair-missing --bundle <pinned bundle> --db <db>`.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import contextmanager
from datetime import date
import json
from pathlib import Path

from backend import baseline_scorer as bs, event_store as store, live_ae

EVALUATION_START = date(2026, 11, 13)  # MYT; L7a: nothing from this day on was used for training
REQUIRED_COLUMNS = {
    'events': ('account_key', 'account_label', 'account_kind', 'source_account_id', 'timestamp', 'source', 'action',
               'resource', 'metadata'),
    'baseline_scores': ('account_key', 'day', 'score', 'tier', 'scored_mode', 'method_sha256'),
    'ml_scores': ('account_key', 'day', 'score', 'flagged', 'threshold', 'model_sha256', 'model_version',
                  'no_resource_today', 'flagged_secondary'),
}


@contextmanager
def _on(db):
    """Point the event store at SQLite file `db` for the block (None: the configured store)."""
    if db is None:
        yield
        return
    if store._PG:
        raise SystemExit('--db is for SQLite files; unset DATABASE_URL (use sqlite-local)')
    saved, store.DB_PATH = store.DB_PATH, Path(db).resolve(strict=True)
    try:
        yield
    finally:
        store.DB_PATH = saved


def _columns(cur, table):
    if store._PG:
        cur.execute('SELECT column_name AS name FROM information_schema.columns WHERE table_name=%s '
                    'AND table_schema = ANY (current_schemas(false))', (table,))
    else:
        cur.execute(f'PRAGMA table_info({table})')
    return {r['name'] for r in store._rows(cur)}


def schema(db=None):
    """{table: [missing column]} for the tables the scorers and readiness read; {} when complete."""
    with _on(db), store._db() as con:
        cur = store._cursor(con)
        have = {t: _columns(cur, t) for t in REQUIRED_COLUMNS}
    missing = {t: [c for c in cols if c not in have[t]] for t, cols in REQUIRED_COLUMNS.items()}
    return {t: cols for t, cols in missing.items() if cols}


def missing_scores(db=None, since=None):
    """Account-days (MYT, >= `since` when given) that have events but no baseline_scores row, or, for lab persona
    accounts (live_ae.scope), no v2 ml_scores row. [{'account_key', 'day', 'timestamp' (one event of that day),
    'missing': ['baseline'?, 'ml'?]}] in account/day order."""
    with _on(db), store._db() as con:
        cur = store._cursor(con)
        tables = {t: _columns(cur, t) for t in ('baseline_scores', 'ml_scores')}
        cur.execute(f'SELECT account_key,{live_ae._COLUMNS} FROM events WHERE account_key IS NOT NULL ORDER BY id')
        accounts = defaultdict(list)
        for r in store._rows(cur):
            accounts[r['account_key']].append(r)
        baseline, ml = set(), set()
        if 'day' in tables['baseline_scores']:
            cur.execute('SELECT account_key,day FROM baseline_scores')
            baseline = {(r['account_key'], r['day']) for r in store._rows(cur)}
        if 'model_version' in tables['ml_scores']:
            cur.execute("SELECT account_key,day FROM ml_scores WHERE model_version='v2'")
            ml = {(r['account_key'], r['day']) for r in store._rows(cur)}
    out = []
    for key in sorted(accounts):
        events = accounts[key]
        persona = live_ae.scope(events) is not None
        first = {}
        for e in events:
            d = bs.myt_day(e['timestamp'])
            if d is not None and (since is None or d >= since):
                first.setdefault(d, e['timestamp'])
        for d in sorted(first):
            day = d.isoformat()
            miss = [name for name, ok in (('baseline', (key, day) in baseline), ('ml', not persona or (key, day) in ml))
                    if not ok]
            if miss:
                out.append({'account_key': key, 'day': day, 'timestamp': first[d], 'missing': miss})
    return out


def comparator(db=None):
    """The comparator this deployment loaded: this process's last load, else live-ae-loaded.json next to the db."""
    state = live_ae.status()
    if state.get('comparator') == 'not_configured' and not store._PG:
        with _on(db):
            path = Path(store.DB_PATH).parent / live_ae.LOADED_FILE
        try:
            state = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            pass
    loaded = state.get('loaded_manifest_sha256')
    return {**state, 'expected_manifest_sha256': live_ae.EXPECTED_MANIFEST_SHA256,
            'ok': state.get('comparator') == 'loaded' and loaded == live_ae.EXPECTED_MANIFEST_SHA256}


def secondary(db=None):
    """{'threshold': declared secondary threshold or None, 'reason', 'unflagged': stored v2 scores without flagged_secondary}."""
    try:
        out = {'threshold': live_ae.secondary_threshold(), 'reason': None}
    except live_ae.Refusal as error:
        out = {'threshold': None, 'reason': str(error)}
    with _on(db), store._db() as con:
        cur = store._cursor(con)
        unflagged = 0
        if 'flagged_secondary' in _columns(cur, 'ml_scores'):
            cur.execute("SELECT COUNT(*) AS n FROM ml_scores WHERE model_version='v2' AND score IS NOT NULL "
                        "AND flagged_secondary IS NULL")
            unflagged = store._rows(cur)[0]['n']
    return {**out, 'unflagged': unflagged}


def events_since(db=None, start=EVALUATION_START):
    """Number of events dated `start` (MYT) or later."""
    with _on(db), store._db() as con:
        cur = store._cursor(con)
        cur.execute('SELECT timestamp FROM events')
        return sum((d := bs.myt_day(r['timestamp'])) is not None and d >= start for r in store._rows(cur))


def report(db=None):
    """Every readiness check; 'ok' only when all pass."""
    missing = missing_scores(db)
    out = {'method': dict(bs.STATUS), 'comparator': comparator(db),
           'missing_scores': {'total': len(missing), 'baseline': sum('baseline' in m['missing'] for m in missing),
                              'ml': sum('ml' in m['missing'] for m in missing)},
           'schema_missing_columns': schema(db), 'events_from_13_nov_myt': events_since(db), 'secondary': secondary(db)}
    out['ok'] = bool(out['method']['scoring_ready'] and out['comparator']['ok'] and not missing
                     and not out['schema_missing_columns'] and out['events_from_13_nov_myt'] > 0
                     and out['secondary']['threshold'] is not None and not out['secondary']['unflagged'])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--db', required=True, help='SQLite events database (the ops store or a workspace copy)')
    r = report(Path(ap.parse_args(argv).db))
    m, c, n = r['method'], r['comparator'], r['missing_scores']
    yes = {True: 'yes', False: 'no'}
    print(f"method binding: {'ok' if m['scoring_ready'] else 'NOT OK'} (sha256 {m['method_sha256']}); {m['reason']}")
    print(f"comparator: {c.get('comparator')}; loaded manifest sha256 {c.get('loaded_manifest_sha256')} == expected "
          f"{c['expected_manifest_sha256']}: {yes[c['ok']]}" + (f"; {c['reason']}" if c.get('reason') else ''))
    sec = r['secondary']
    print(f"secondary threshold: {sec['threshold'] if sec['threshold'] is not None else 'ABSENT (' + sec['reason'] + ')'}"
          f"; stored v2 scores without flagged_secondary: {sec['unflagged']}")
    print(f"missing scores: {n['total']} account-days (baseline {n['baseline']}, ml {n['ml']})")
    s = r['schema_missing_columns']
    print('schema columns: ' + ('all present' if not s else 'MISSING ' + ', '.join(f'{t}.{col}' for t, cols in s.items() for col in cols)))
    print(f"events dated 13 Nov 2026 MYT or later: {r['events_from_13_nov_myt']}")
    print('READY' if r['ok'] else 'NOT READY')
    raise SystemExit(0 if r['ok'] else 1)


if __name__ == '__main__':
    main()

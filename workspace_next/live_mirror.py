"""Live mirror: follows the pilot's collected events into the workspace COPY (never the other way round).

    python -m workspace_next.live_mirror --source <live events.db> --dest <preview root>/preview.db [--interval 60] [--once]

The source is opened read-only (?mode=ro). Only new `events` and `alerts` rows are added to the copy, so
analyst edits always win. analyst_*, identity_* and workspace_* tables are not touched.

Baseline scores: the copy is scored by the BACKEND scorer (backend.baseline_scorer.on_event, the same call the
ingest service makes), applied to the account-days of the events this pass copied. Source alerts of type
baseline_risk are not copied: the copy holds its own, derived by that same function from the same events.
Because the copy creates baseline findings itself, copied source alerts get copy-local ids and are matched by
`alerts.mirror_source_id` (a copy-only column), so a source alert id can never collide with a copy finding.
Also holds the read-only /workspace/live-feed view model.
"""
import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
from unittest import mock

from backend import baseline_scorer, collector_status, event_store as store
from workspace_next import baseline_score as bs, operations, system_accounts

MYT = bs.MYT
# Study guard: until GUARD_END the copy must hold nothing from GUARD_START onward (one constant, tested).
GUARD_START = datetime(2026, 11, 14, tzinfo=MYT)
GUARD_END = datetime(2026, 11, 16, tzinfo=MYT)
PILOT_DATA = Path(r'C:\Users\yyzhe\.codex\worktrees\argus-cloud-live\fyp-ueba\data\live')
PILOT_SOURCE_ROOT = Path(r'C:\Users\yyzhe\.codex\worktrees\clue-benchmark-replay\fyp-ueba')
PILOT_TICK = PILOT_DATA / 'pilot-local-v1' / 'last_tick.json'
STATUS_FILE = 'mirror-status.json'
SOURCES = ('aws_cloudtrail', 'github_events', 'cloudflare_access')
NEWEST, RAW_NEWEST = 8, 200  # lines shown per source; repeats are collapsed from the newest RAW_NEWEST events
_EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
_ACCOUNT = re.compile(r'\d{12}')


def guard_active(now=None):
    return (now or datetime.now(timezone.utc)) < GUARD_END


def blocked(value, now=None):
    """True when `value` (an ISO timestamp) must not enter the copy yet. Unparseable = blocked while the guard is on."""
    if not guard_active(now):
        return False
    try:
        return bs._stamp(value) >= GUARD_START
    except (ValueError, TypeError):
        return True


def _write_json(path, value):
    tmp = Path(str(path) + '.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    os.replace(tmp, path)


def _marker_ok(dest):
    marker = Path(dest).parent / 'workspace-copy.json'
    try:
        declared = json.loads(marker.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return False
    return (declared.get('not_live') is True and Path(declared.get('copy_db', '')).resolve() == Path(dest).resolve())


def _new_rows(src, dst, table, key, keep):
    """Rows of `table` in src whose key is absent from dst and that `keep` accepts, as (columns, rows)."""
    have = {r[0] for r in dst.execute(f'SELECT {key} FROM {table}')}
    cols = [r[1] for r in dst.execute(f'PRAGMA table_info({table})')]
    src_cols = {r[1] for r in src.execute(f'PRAGMA table_info({table})')}
    cols = [c for c in cols if c in src_cols]
    quoted = ','.join(f'"{c}"' for c in cols)
    rows = [r for r in src.execute(f'SELECT {quoted} FROM {table} ORDER BY {key}') if r[cols.index(key)] not in have]
    return quoted, cols, [r for r in rows if keep(dict(zip(cols, r)))]


def snapshot(root, now=None):
    """Refresh operations-snapshot.json from the pilot's own status files (read-only). Reuses operations.capture;
    the per-source workload ledgers are skipped (one is a live WAL database) so that history stays 'unavailable'."""
    out = Path(root) / 'operations-snapshot.json'
    tmp = Path(str(out) + '.tmp')
    with mock.patch.object(operations, 'workload_history', lambda path, day: {'available': False, 'day': day}):
        operations.capture(PILOT_DATA / 'connected', PILOT_SOURCE_ROOT, tmp)
    os.replace(tmp, out)


@contextmanager
def _on_copy(dest):
    """Point the backend event store at the SQLite copy for one call (never PostgreSQL)."""
    if store._PG:
        raise SystemExit('Refusing to run: the workspace copy is SQLite only; set DATABASE_URL=sqlite-local')
    saved = store.DB_PATH
    store.DB_PATH = Path(dest)
    try:
        yield
    finally:
        store.DB_PATH = saved


def backfill_copy(dest, now=None):
    """`python -m backend.baseline_scorer --backfill` on a copy: recompute every stored account-day."""
    with _on_copy(dest):
        baseline_scorer.ensure_schema()
        return baseline_scorer.backfill(now)


LEGACY = 'workspace_baseline_alerts'  # pre-L8 copy-only baseline findings (ids exposed as 1_000_000 + rowid)


def adopt_legacy(dest):
    """One-off: carry analyst decisions from the pre-L8 copy-only table onto the backend's baseline findings
    (matched by account and day), repoint case links and audit rows to the new ids, then rename the old table."""
    with closing(sqlite3.connect(str(dest), timeout=15)) as con, con:
        con.row_factory = sqlite3.Row
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if LEGACY not in tables:
            return None
        moved = orphaned = 0
        for old in con.execute(f'SELECT * FROM {LEGACY}').fetchall():
            new = con.execute('SELECT id,details FROM alerts WHERE alert_type=? AND user_id=? AND day=?',
                              (bs.ALERT_TYPE, old['account_key'], old['day'])).fetchone()
            if new is None:
                orphaned += 1
                continue
            details = json.loads(old['details'] or '{}')
            if details.get('analyst_touched') or (old['status'] != 'Open' and not details.get('auto_resolved')):
                kept = json.loads(new['details'] or '{}')
                kept.pop('auto_resolved', None)
                kept['analyst_touched'] = True
                con.execute('UPDATE alerts SET status=?,resolved_at=?,details=? WHERE id=?',
                            (old['status'], old['resolved_at'], json.dumps(kept), new['id']))
            old_id = 1_000_000 + old['id']
            if 'analyst_case_links' in tables:
                con.execute("UPDATE analyst_case_links SET target=? WHERE kind='finding' AND target=?", (str(new['id']), str(old_id)))
            if 'workspace_finding_audit' in tables:
                con.execute('UPDATE workspace_finding_audit SET finding_id=? WHERE finding_id=?', (new['id'], old_id))
            moved += 1
        con.execute(f'ALTER TABLE {LEGACY} RENAME TO {LEGACY}_pre_l8')
    return {'moved': moved, 'orphaned': orphaned}


def prepare_copy(dest):
    """Workspace start-up: score a never-scored copy once with the backend backfill, then adopt legacy findings."""
    with closing(sqlite3.connect(f'file:{Path(dest).resolve().as_posix()}?mode=ro', uri=True)) as con:
        scored = con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='baseline_scores'").fetchone()
    result = {'backfill': None if scored else backfill_copy(dest)}
    result['legacy'] = adopt_legacy(dest)
    return result


def _copy_alerts(src, dst, now):
    """New non-baseline source alerts, inserted with copy-local ids; matched by mirror_source_id."""
    cols = [r[1] for r in dst.execute('PRAGMA table_info(alerts)')]
    if 'mirror_source_id' not in cols:
        dst.execute('ALTER TABLE alerts ADD COLUMN mirror_source_id INTEGER')
        # rows copied before this column existed kept their source id as their own id
        dst.execute('UPDATE alerts SET mirror_source_id=id WHERE alert_type!=?', (bs.ALERT_TYPE,))
    have = {r[0] for r in dst.execute('SELECT mirror_source_id FROM alerts WHERE mirror_source_id IS NOT NULL')}
    src_cols = {r[1] for r in src.execute('PRAGMA table_info(alerts)')}
    cols = [c for c in cols if c in src_cols and c not in ('id', 'day', 'mirror_source_id')]
    quoted = ','.join(f'"{c}"' for c in cols)
    rows = [r for r in src.execute(f'SELECT id,{quoted} FROM alerts WHERE alert_type!=? ORDER BY id', (bs.ALERT_TYPE,))
            if r[0] not in have and not blocked(r[1 + cols.index('created_at')], now)]
    dst.executemany(f'INSERT INTO alerts ({quoted},mirror_source_id) VALUES ({",".join("?" * (len(cols) + 1))})',
                    [(*r[1:], r[0]) for r in rows])
    return rows


def _rescore(dest, events, cols, now):
    """Backend per-account-day recompute for the account-days this pass copied."""
    key_i, ts_i = cols.index('account_key'), cols.index('timestamp')
    todo = {}
    for r in events:
        day = baseline_scorer.myt_day(r[ts_i])
        if r[key_i] and day:
            todo.setdefault((r[key_i], day), r[ts_i])
    with _on_copy(dest):
        baseline_scorer.ensure_schema()
        for (key, _), ts in sorted(todo.items()):
            baseline_scorer.on_event(key, ts, now)
    return len(todo)


def run_pass(source, dest, now=None, tick_snapshot=True):
    """One mirror pass. Returns the status dict, or None when skipped (source busy). Never deletes anything."""
    now = now or datetime.now(timezone.utc)
    source, dest = Path(source).resolve(), Path(dest).resolve()
    if source == dest or not _marker_ok(dest):
        raise SystemExit('Refusing to run: dest must be a marked workspace copy (workspace-copy.json with not_live: true)')
    if store._PG:
        raise SystemExit('Refusing to run: the workspace copy is SQLite only; set DATABASE_URL=sqlite-local')
    try:
        with closing(sqlite3.connect(f'file:{source.as_posix()}?mode=ro', uri=True, timeout=3)) as src, \
                closing(sqlite3.connect(str(dest), timeout=15)) as dst:
            src.execute('BEGIN')  # one short read transaction
            ev_q, ev_cols, events = _new_rows(src, dst, 'events', 'id', lambda r: not blocked(r['timestamp'], now))
            latest = [r[0] for r in src.execute('SELECT timestamp FROM events ORDER BY id DESC LIMIT 200')]
            with dst:
                dst.executemany(f'INSERT OR IGNORE INTO events ({ev_q}) VALUES ({",".join("?" * len(ev_cols))})', events)
                alerts = _copy_alerts(src, dst, now)
            src.rollback()
    except sqlite3.OperationalError as error:
        print(f'[mirror] pass skipped: {type(error).__name__}', file=sys.stderr)
        return None
    stamps = []
    for value in latest:
        try: stamps.append(bs._stamp(value))
        except (ValueError, TypeError): pass
    rescored = _rescore(dest, events, ev_cols, now)
    status = {'last_pass_utc': now.isoformat(), 'events_added': len(events), 'alerts_added': len(alerts),
              'source_latest_event_utc': max(stamps).astimezone(timezone.utc).isoformat() if stamps else None,
              'guard_active': guard_active(now), 'account_days_rescored': rescored}
    _write_json(dest.parent / STATUS_FILE, status)
    if tick_snapshot:
        try: snapshot(dest.parent, now)
        except (OSError, ValueError, TypeError) as error: print(f'[mirror] snapshot failed: {type(error).__name__}', file=sys.stderr)
    return status


# --- live feed view model --------------------------------------------------------------------------

def _clean(value):
    if not isinstance(value, str): return value
    return _ACCOUNT.sub('[account hidden]', _EMAIL.sub('[email hidden]', value))


def _read(path):
    return collector_status.read_status(path)


def read_status_file(root):
    return _read(Path(root) / STATUS_FILE)


def collapse(events):
    """Newest-first events: consecutive same (account_label, action) become one line with `count`; the first (latest) is kept."""
    out = []
    for e in events:
        if out and (out[-1]['account_label'], out[-1]['action']) == (e['account_label'], e['action']):
            out[-1]['count'] += 1
        else:
            out.append({**e, 'count': 1})
    return out


def feed(db, root, now=None, tick_path=PILOT_TICK):
    """Per-source freshness plus the newest events. No IPs, payloads, emails or account numbers."""
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(MYT).date()
    out = {s: {'last_received_utc': None, 'events_last_hour': 0, 'events_today_myt': 0, 'newest': []} for s in SOURCES}
    with closing(sqlite3.connect(f'file:{Path(db).resolve().as_posix()}?mode=ro', uri=True, timeout=3)) as con:
        rows = con.execute('SELECT source,timestamp,ingested_at,account_label,action,account_kind FROM events ORDER BY id DESC LIMIT 5000').fetchall()
    parsed = []
    declared = system_accounts.declared(db)
    for source, ts, ingested, label, action, kind in rows:
        if source not in out: continue
        try: parsed.append((source, bs._stamp(ts), bs._stamp(ingested).astimezone(timezone.utc), label, action,
                                system_accounts.is_infrastructure(label, kind, source, declared)))
        except (ValueError, TypeError): continue
    for source, when, received, label, action, infra in sorted(parsed, key=lambda r: r[1], reverse=True):
        item = out[source]
        if item['last_received_utc'] is None or received.isoformat() > item['last_received_utc']:
            item['last_received_utc'] = received.isoformat()
        if now - received <= timedelta(hours=1): item['events_last_hour'] += 1
        if when.date() == today: item['events_today_myt'] += 1
        if len(item['newest']) < RAW_NEWEST:
            item['newest'].append({'time_myt': when.isoformat(), 'account_label': _clean(label or 'Unknown account'),
                                   'action': _clean(action), 'received_seconds_ago': max(0, int((now - received).total_seconds())), 'infrastructure': infra})
    for item in out.values():
        item['newest'] = collapse(item['newest'])[:NEWEST]
    tick = _read(tick_path)
    collector = {'last_tick_utc': None, 'ok': None}
    if tick:
        try: collector = {'last_tick_utc': bs._stamp(tick['at_utc']).astimezone(timezone.utc).isoformat(), 'ok': bool(tick.get('ok'))}
        except (KeyError, ValueError, TypeError): pass
    return {'now_utc': now.isoformat(), 'sources': out, 'mirror': _read(Path(root) / STATUS_FILE), 'collector': collector}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source', required=True)
    ap.add_argument('--dest', required=True)
    ap.add_argument('--interval', type=int, default=60)
    ap.add_argument('--once', action='store_true')
    args = ap.parse_args(argv)
    while True:
        try:
            status = run_pass(args.source, args.dest)
            if status: print(f"[mirror] {status['last_pass_utc']} +{status['events_added']} events +{status['alerts_added']} alerts", flush=True)
        except SystemExit:
            raise
        except Exception as error:  # a failed pass is logged and retried; nothing is deleted
            print(f'[mirror] pass failed: {type(error).__name__}', file=sys.stderr, flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == '__main__':
    main()

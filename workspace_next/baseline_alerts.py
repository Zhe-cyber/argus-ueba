"""Baseline-score findings: one row per (account, MYT day) whose baseline tier is Medium or High.

Stored in workspace_baseline_alerts (copy DB only; the shared `alerts` table is never touched).
Row ids are exposed as ID_OFFSET + rowid so they cannot collide with alerts.id.
Analyst status is never overwritten, except the documented auto-resolve below.
"""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import sqlite3

from workspace_next import baseline_score as bs

ID_OFFSET = 1_000_000
ALERT_TYPE = 'baseline_risk'
DDL = ('''CREATE TABLE IF NOT EXISTS workspace_baseline_alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL, alert_type TEXT NOT NULL,
    severity TEXT NOT NULL, title TEXT NOT NULL, details TEXT DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'Open', created_at TEXT NOT NULL, resolved_at TEXT,
    account_key TEXT NOT NULL, day TEXT NOT NULL, UNIQUE(account_key, day))''',
       '''CREATE TABLE IF NOT EXISTS workspace_finding_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, finding_id INTEGER NOT NULL, old_status TEXT,
    new_status TEXT NOT NULL, analyst TEXT NOT NULL, reason TEXT NOT NULL, at_utc TEXT NOT NULL)''')


def ensure(cur):
    for statement in DDL:
        cur.execute(statement)


def as_alert(row):
    """Alerts-shaped dict with the offset id (row is a mapping with the table's columns)."""
    row = dict(row)
    row['id'] = ID_OFFSET + row['id']
    return row


def get(cur, finding_id, ph='?'):
    """One baseline finding by exposed id, or None. Tolerates a missing table."""
    if finding_id < ID_OFFSET:
        return None
    try:
        cur.execute(f'SELECT * FROM workspace_baseline_alerts WHERE id={ph}', (finding_id - ID_OFFSET,))
    except sqlite3.OperationalError:
        return None
    row = cur.fetchone()
    return as_alert(row) if row else None


def _created(day, now):
    end = datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=bs.MYT) - timedelta(seconds=1)
    return min(end, now).astimezone(timezone.utc).isoformat()


def sync(db, now=None):
    """Upsert Medium/High account-days; auto-resolve untouched Open rows that fell below Medium. Returns counts."""
    now = now or datetime.now(timezone.utc)
    wanted = {}
    for key, acct in bs.load(db).items():
        for day in acct['days']:
            result = bs.score_day(acct['days'], day)
            if result['tier'] in ('Medium', 'High'):
                wanted[(key, result['day'])] = (acct, result)
    stats = {'inserted': 0, 'updated': 0, 'auto_resolved': 0, 'reopened': 0}
    with closing(sqlite3.connect(str(db), timeout=15)) as con, con:
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        ensure(cur)
        existing = {(r['account_key'], r['day']): r for r in cur.execute('SELECT * FROM workspace_baseline_alerts').fetchall()}
        for (key, day), (acct, r) in wanted.items():
            details = {k: r[k] for k in ('day', 'score', 'tier', 'signals', 'facts', 'history_days', 'events_today', 'partial')}
            details['source'] = acct['source']
            title = f"Baseline risk {r['tier']} ({r['score']}): {acct['label'] or key}"
            row = existing.get((key, day))
            if row is None:
                cur.execute('INSERT INTO workspace_baseline_alerts (user_id,alert_type,severity,title,details,status,created_at,account_key,day)'
                            " VALUES (?,?,?,?,?,'Open',?,?,?)",
                            (key, ALERT_TYPE, r['tier'], title, json.dumps(details),
                             _created(datetime.strptime(day, '%Y-%m-%d').date(), now), key, day))
                stats['inserted'] += 1
                continue
            old = json.loads(row['details'] or '{}')
            if old.get('analyst_touched'): details['analyst_touched'] = old['analyst_touched']
            status, resolved = row['status'], row['resolved_at']
            if old.get('auto_resolved'):
                if status == 'Resolved':  # Medium+ again: undo only our own auto-resolve
                    status, resolved = 'Open', None
                    stats['reopened'] += 1
                else:
                    details['auto_resolved'] = old['auto_resolved']
            cur.execute('UPDATE workspace_baseline_alerts SET severity=?,title=?,details=?,status=?,resolved_at=? WHERE id=?',
                        (r['tier'], title, json.dumps(details), status, resolved, row['id']))
            stats['updated'] += 1
        for (key, day), row in existing.items():
            if (key, day) in wanted or row['status'] != 'Open':
                continue
            old = json.loads(row['details'] or '{}')
            if old.get('analyst_touched'):
                continue  # an analyst reopened it; their decision stands
            old['auto_resolved'] = 'score fell below Medium'
            cur.execute("UPDATE workspace_baseline_alerts SET status='Resolved',resolved_at=?,details=? WHERE id=?",
                        (now.isoformat(), json.dumps(old), row['id']))
            stats['auto_resolved'] += 1
    return stats

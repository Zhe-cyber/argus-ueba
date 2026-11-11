"""L4 rehearsal: copy the demo DB into a separate rehearsal root and add SIMULATED persona-02 events.

Scenario "Batch reporter goes rogue" (same counts as scripts/demo_scenario_live.py). Simulated rows carry
event_id 'sim-<uuid>' and metadata {"simulated": true, "scenario": "L4"}. Never run against the live DB or
the demo copy itself: the source is only read (sqlite backup, mode=ro); everything is written under --root.
"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MYT = timezone(timedelta(hours=8))
PERSONA = 'persona-02'
START_MIN, END_MIN = 21 * 60 + 5, 21 * 60 + 25  # 21:05-21:25 MYT
# (action, bucket symbol) in execution order; counts are the spec's and must not be tuned.
AWS_PLAN = ([('GetBucketLocation', s) for s in ('confidential', 'p04', 'p05', 'p06')]
            + [('GetObject', 'confidential')] * 12
            + [('GetObject', s) for s in ('p04', 'p05', 'p06') for _ in range(6)]
            + [('ListObjectsV2', 'confidential')])
CF_COUNT = 8


def closed_day(now=None):
    """Latest closed MYT calendar day (yesterday, MYT)."""
    return ((now or datetime.now(timezone.utc)).astimezone(MYT) - timedelta(days=1)).date()


def stamps(day, n):
    """n timestamps evenly spread over 21:05-21:25 MYT on `day`, as UTC '%Y-%m-%dT%H:%M:%SZ'."""
    base = datetime.combine(day, datetime.min.time(), tzinfo=MYT)
    step = (END_MIN - START_MIN) * 60 / max(n - 1, 1)
    return [(base + timedelta(minutes=START_MIN, seconds=round(i * step))).astimezone(timezone.utc)
            .strftime('%Y-%m-%dT%H:%M:%SZ') for i in range(n)]


def _template(con, where, args):
    con.row_factory = sqlite3.Row
    row = con.execute(f'SELECT * FROM events WHERE {where} ORDER BY id DESC LIMIT 1', args).fetchone()
    if row is None:
        raise SystemExit('persona-02 template row not found; stop and escalate')
    return dict(row)


def build_rows(aws_tpl, cf_tpl, day, now=None):
    """Simulated event dicts (no id). Only event_id/timestamp/action/resource/ingested_at/metadata differ from the templates."""
    if not re.search(r'-(p\d\d|confidential)$', aws_tpl['resource']) or '/workloads/persona-02/' not in cf_tpl['resource']:
        raise SystemExit('persona-02 row shape is not the expected one; stop and escalate')
    now = (now or datetime.now(timezone.utc)).isoformat()
    meta = {'simulated': True, 'scenario': 'L4'}
    times = stamps(day, len(AWS_PLAN) + CF_COUNT)
    rows = []
    for (action, symbol), ts in zip(AWS_PLAN, times):
        m = dict(meta, **({'errorCode': 'AccessDenied'} if action == 'ListObjectsV2' else {}))
        rows.append({**aws_tpl, 'event_id': f'sim-{uuid4()}', 'timestamp': ts, 'action': action, 'ingested_at': now,
                     'resource': re.sub(r'-(p\d\d|confidential)$', '-' + symbol, aws_tpl['resource']),
                     'metadata': json.dumps(m)})
    host = cf_tpl['resource'].split('/workloads/')[0]
    for n, ts in enumerate(times[len(AWS_PLAN):], 1):
        rows.append({**cf_tpl, 'event_id': f'sim-{uuid4()}', 'timestamp': ts, 'ingested_at': now,
                     'resource': f'{host}/workloads/{PERSONA}/demo-{n}', 'metadata': json.dumps(meta)})
    for r in rows:  # digest of what is actually stored, so no real payload digest is reused
        r['payload_digest'] = hashlib.sha256(json.dumps([r['event_id'], r['timestamp'], r['action'], r['resource']]).encode()).hexdigest()
    return rows


def insert(db, rows):
    with sqlite3.connect(str(db)) as con:
        cols = [r[1] for r in con.execute('PRAGMA table_info(events)') if r[1] != 'id']
        con.executemany(f'INSERT INTO events ({",".join(chr(34) + c + chr(34) for c in cols)}) VALUES ({",".join("?" * len(cols))})',
                        [[r[c] for c in cols] for r in rows])


def prune_after(db, day):
    """Rehearsal copy only: drop events dated after `day` (MYT) so `day` is the latest day the UI shows by default."""
    from workspace_next import baseline_score as bs
    with sqlite3.connect(str(db)) as con:
        late = [i for i, ts in con.execute('SELECT id,timestamp FROM events') if _myt_date(bs, ts) is not None and _myt_date(bs, ts) > day]
        con.executemany('DELETE FROM events WHERE id=?', [(i,) for i in late])
    return len(late)


def _myt_date(bs, ts):
    try:
        return bs._stamp(ts).date()
    except (ValueError, TypeError):
        return None


def prepare(src_dir, root):
    """Validate the source marker and copy the DB + declaration files into root; returns the new DB path."""
    src_dir, root = Path(src_dir).resolve(), Path(root).resolve()
    try:
        marker = json.loads((src_dir / 'workspace-copy.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        raise SystemExit('source folder has no valid workspace-copy.json')
    if marker.get('not_live') is not True or Path(marker.get('copy_db', '')).resolve() != src_dir / 'preview.db':
        raise SystemExit('source is not a marked not_live workspace copy; refusing')
    if root == src_dir:
        raise SystemExit('rehearsal root must differ from the source')
    root.mkdir(parents=True, exist_ok=True)
    dest = root / 'preview.db'
    if dest.exists():
        raise SystemExit('rehearsal root already holds a preview.db; remove it deliberately first')
    with sqlite3.connect(f'file:{(src_dir / "preview.db").as_posix()}?mode=ro', uri=True) as s, sqlite3.connect(str(dest)) as d:
        s.backup(d)
    for name in ('workload-groups.json', 'system-accounts.json', 'operations-snapshot.json'):
        if (src_dir / name).is_file():
            shutil.copyfile(src_dir / name, root / name)
    (root / 'workspace-copy.json').write_text(json.dumps({'not_live': True, 'rehearsal': True, 'copy_db': str(dest)}, indent=2), encoding='utf-8')
    return dest


def persona_keys(root):
    g = next(x for x in json.loads((Path(root) / 'workload-groups.json').read_text(encoding='utf-8')) if x['group'] == PERSONA)
    return g['members']


def report(db, root, day):
    """Labels and numbers only."""
    from workspace_next import baseline_score as bs, workload_groups
    accounts = bs.load(db)
    for key in persona_keys(root):
        a = accounts[key]
        r = bs.score_day(a['days'], day)
        print(f"{a['source']} ({a['kind']}): score={r['score']} tier={r['tier']} events_today={r['events_today']} "
              f"history_days={r['history_days']} rho_action={r.get('rho_action')} rho_resource={r.get('rho_resource')}")
        print('  signals:', ', '.join(f'{k}={v}' for k, v in r['signals'].items()))
    g = next(x for x in workload_groups.groups(db, Path(root) / 'workload-groups.json', day.isoformat())['groups'] if x['group'] == PERSONA)
    print(f"group {PERSONA}: score={g['group_score']} tier={g['tier']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--from', dest='src', required=True, help='demo copy DB path (its folder must hold a not_live marker)')
    ap.add_argument('--root', required=True, help='new rehearsal root (separate from the demo copy)')
    args = ap.parse_args()
    from workspace_next import baseline_alerts
    db = prepare(Path(args.src).parent, args.root)
    day = closed_day()
    print(f'dropped {prune_after(db, day)} real events dated after {day.isoformat()} from the rehearsal copy only')
    keys = persona_keys(db.parent)
    with sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True) as con:
        aws = _template(con, "account_key=? AND source='aws_cloudtrail' AND action='GetObject'", (keys[0],))
        cf = _template(con, "account_key=? AND source='cloudflare_access'", (keys[1],))
    rows = build_rows(aws, cf, day)
    insert(db, rows)
    print(f'inserted {len(rows)} simulated rows for {day.isoformat()} (MYT) into the rehearsal copy')
    print('baseline sync:', baseline_alerts.sync(db))
    report(db, db.parent, day)


if __name__ == '__main__':
    main()

"""Rehearsal of the live evaluation scenarios S1-S4 (specs/L7-live-evaluation-rules.md section 2) on a SIMULATED copy.

    python scripts/demo_scenario_sim.py --from data/live/live-v1-preview/preview.db --root data/live/live-v1-rehearsal [--scenario ALL|S1|S2|S3|S4]

Copies the demo DB (only if its folder holds a not_live marker) into a new rehearsal root, then adds the scenario's
SIMULATED events, each scenario on its own day after the latest real day (S1 = +1 day ... S4 = +4 days), and scores
them with the backend scorer (backend.baseline_scorer.on_event, the ingest call). Simulated rows carry event_id
'sim-<uuid>' and metadata {"simulated": true, "scenario": "<S1..S4>"}. Never run against the live DB or the demo copy
itself: the source is only read (sqlite backup, mode=ro); everything is written under --root. Prints numbers only.
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
from scripts import demo_scenario_live as live  # import-time safe: constants and pure helpers only

MYT = timezone(timedelta(hours=8))
PERSONA = 'persona-02'
ORDER = ('S1', 'S2', 'S3', 'S4')
# Simulated MYT minutes (first, last call), inside each scenario's live window; counts come from live.SCENARIOS.
SIM_MINUTES = {'S1': (21 * 60 + 5, 21 * 60 + 25), 'S2': (21 * 60 + 5, 21 * 60 + 45),
               'S3': (14 * 60, 14 * 60), 'S4': (14 * 60, 14 * 60 + 1)}
CF_COUNT = live.MAX_CF


def closed_day(now=None):
    """Latest closed MYT calendar day (yesterday, MYT)."""
    return ((now or datetime.now(timezone.utc)).astimezone(MYT) - timedelta(days=1)).date()


def stamps(day, n, start=SIM_MINUTES['S1'][0], end=SIM_MINUTES['S1'][1]):
    """n timestamps evenly spread over [start, end] MYT minutes on `day`, as UTC '%Y-%m-%dT%H:%M:%SZ'."""
    base = datetime.combine(day, datetime.min.time(), tzinfo=MYT)
    step = (end - start) * 60 / max(n - 1, 1)
    return [(base + timedelta(minutes=start, seconds=round(i * step))).astimezone(timezone.utc)
            .strftime('%Y-%m-%dT%H:%M:%SZ') for i in range(n)]


def _template(con, where, args):
    con.row_factory = sqlite3.Row
    row = con.execute(f'SELECT * FROM events WHERE {where} ORDER BY id DESC LIMIT 1', args).fetchone()
    if row is None:
        raise SystemExit('persona template row not found; stop and escalate')
    return dict(row)


def build_rows(aws_tpl, cf_tpl, day, now=None, scenario='S1'):
    """Simulated event dicts (no id). Only event_id/timestamp/action/resource/ingested_at/metadata differ from the templates."""
    plan = live.SCENARIOS[scenario]
    if not re.search(r'-(p\d\d|confidential)$', aws_tpl['resource']):
        raise SystemExit('persona row shape is not the expected one; stop and escalate')
    with_cf = plan['cloudflare']
    if with_cf and f"/workloads/{plan['persona']}/" not in cf_tpl['resource']:
        raise SystemExit('persona Cloudflare row shape is not the expected one; stop and escalate')
    now = (now or datetime.now(timezone.utc)).isoformat()
    meta = {'simulated': True, 'scenario': scenario}
    aws_calls = live.calls(plan)
    times = stamps(day, len(aws_calls) + (CF_COUNT if with_cf else 0), *SIM_MINUTES[scenario])
    rows = []
    for (_, action, symbol), ts in zip(aws_calls, times):
        m = dict(meta, **({'errorCode': 'AccessDenied'} if action == 'ListObjectsV2' else {}))
        rows.append({**aws_tpl, 'event_id': f'sim-{uuid4()}', 'timestamp': ts, 'action': action, 'ingested_at': now,
                     'resource': re.sub(r'-(p\d\d|confidential)$', '-' + symbol, aws_tpl['resource']),
                     'metadata': json.dumps(m)})
    if with_cf:
        host = cf_tpl['resource'].split('/workloads/')[0]
        for n, ts in enumerate(times[len(aws_calls):], 1):
            rows.append({**cf_tpl, 'event_id': f'sim-{uuid4()}', 'timestamp': ts, 'ingested_at': now,
                         'resource': f"{host}/workloads/{plan['persona']}/demo-{n}", 'metadata': json.dumps(meta)})
    for r in rows:  # digest of what is actually stored, so no real payload digest is reused
        r['payload_digest'] = hashlib.sha256(json.dumps([r['event_id'], r['timestamp'], r['action'], r['resource']]).encode()).hexdigest()
    return rows


def insert(db, rows):
    with sqlite3.connect(str(db)) as con:
        cols = [r[1] for r in con.execute('PRAGMA table_info(events)') if r[1] != 'id']
        con.executemany(f'INSERT INTO events ({",".join(chr(34) + c + chr(34) for c in cols)}) VALUES ({",".join("?" * len(cols))})',
                        [[r[c] for c in cols] for r in rows])
    con.close()


def latest_real_day(db):
    from backend.baseline_scorer import myt_day
    with sqlite3.connect(f'file:{Path(db).as_posix()}?mode=ro', uri=True) as con:
        days = [myt_day(ts) for (ts,) in con.execute("SELECT timestamp FROM events WHERE event_id IS NULL OR event_id NOT LIKE 'sim-%'")]
    con.close()
    return max(d for d in days if d)


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


def persona_keys(root, persona=PERSONA):
    g = next(x for x in json.loads((Path(root) / 'workload-groups.json').read_text(encoding='utf-8')) if x['group'] == persona)
    return g['members']  # [AWS role, Cloudflare token] as written by workload_groups.generate


def rehearse(db, scenario, day):
    """Insert one scenario's simulated rows on `day` and score them through the backend scorer."""
    from backend import baseline_scorer
    from workspace_next import live_mirror
    plan = live.SCENARIOS[scenario]
    keys = persona_keys(db.parent, plan['persona'])
    with sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True) as con:
        aws = _template(con, "account_key=? AND source='aws_cloudtrail' AND action='GetObject'", (keys[0],))
        cf = _template(con, "account_key=? AND source='cloudflare_access'", (keys[1],)) if plan['cloudflare'] else None
    con.close()
    rows = build_rows(aws, cf, day, scenario=scenario)
    insert(db, rows)
    with live_mirror._on_copy(db):
        for key in {r['account_key'] for r in rows}:
            baseline_scorer.on_event(key, rows[0]['timestamp'])
    return keys, len(rows)


def report(db, scenario, keys, day):
    """Labels and numbers only."""
    from workspace_next import baseline_score as bs, workload_groups
    plan = live.SCENARIOS[scenario]
    ident = bs._identities(db)
    print(f"{scenario} {plan['persona']} on {day.isoformat()} (expected, stated in advance: {plan['expected']})")
    for key in keys[:2 if plan['cloudflare'] else 1]:
        r = bs._scores(db, 'WHERE account_key=? AND day=?', (key, day.isoformat()))[0][1]
        print(f"  {ident[key][2]}: score={r['score']} tier={r['tier']} events_today={r['events_today']} "
              f"history_days={r['history_days']} rho_action={r.get('rho_action')} rho_resource={r.get('rho_resource')}")
        print('    signals:', ', '.join(f'{k}={v}' for k, v in r['signals'].items()))
    if plan['cloudflare']:
        g = next(x for x in workload_groups.groups(db, db.parent / 'workload-groups.json', day.isoformat())['groups']
                 if x['group'] == plan['persona'])
        print(f"  workload group {plan['persona']}: score={g['group_score']} tier={g['tier']}")
    with sqlite3.connect(f'file:{db.as_posix()}?mode=ro', uri=True) as con:
        found = con.execute("SELECT severity FROM alerts WHERE alert_type='baseline_risk' AND user_id=? AND day=?",
                            (keys[0], day.isoformat())).fetchone()
    con.close()
    print(f"  baseline finding raised: {'yes (' + found[0] + ')' if found else 'no'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--from', dest='src', required=True, help='demo copy DB path (its folder must hold a not_live marker)')
    ap.add_argument('--root', required=True, help='new rehearsal root (separate from the demo copy)')
    ap.add_argument('--scenario', choices=('ALL',) + ORDER, default='ALL')
    args = ap.parse_args()
    from workspace_next import live_mirror
    db = prepare(Path(args.src).parent, args.root)
    print('copy prepared:', live_mirror.prepare_copy(db))
    base = latest_real_day(db)
    for scenario in (ORDER if args.scenario == 'ALL' else (args.scenario,)):
        day = base + timedelta(days=ORDER.index(scenario) + 1)
        keys, n = rehearse(db, scenario, day)
        print(f'inserted {n} simulated rows for {scenario} on {day.isoformat()} (MYT) into the rehearsal copy')
        report(db, scenario, keys, day)


if __name__ == '__main__':
    main()
